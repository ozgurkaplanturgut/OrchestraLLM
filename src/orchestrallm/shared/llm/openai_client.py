from __future__ import annotations

import json
import logging
import time
from typing import AsyncGenerator, Dict, List, Optional, Sequence

import httpx

from orchestrallm.shared.config.settings import settings
from orchestrallm.shared.concurrency import LLM_STREAM_SEMAPHORE

log = logging.getLogger("openai")

_CHAT_URL = f"{settings.OPENAI_BASE_URL.rstrip('/')}/chat/completions"
_EMB_URL  = f"{settings.OPENAI_BASE_URL.rstrip('/')}/embeddings"

def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

async def stream_chat(
    messages: List[Dict[str, str]],
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    request_timeout: Optional[int] = None,
) -> AsyncGenerator[str, None]:
    """ 
    This function streams chat completions from the OpenAI API.
    """
    payload = {
        "model": (model or settings.CHAT_MODEL),
        "messages": messages,
        "temperature": temperature if temperature is not None else settings.TEMPERATURE,
        "stream": True,
        "max_tokens": max_tokens if max_tokens is not None else settings.MAX_TOKENS,
    }
    timeout = httpx.Timeout(request_timeout or settings.LLM_REQUEST_TIMEOUT)

    async with LLM_STREAM_SEMAPHORE:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", _CHAT_URL, headers=_headers(), json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[len("data: "):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        j = json.loads(data)
                        delta = j["choices"][0].get("delta", {})
                        tok = delta.get("content")
                        if tok:
                            yield tok
                    except Exception:
                        continue

async def complete_chat(
    messages: List[Dict[str, str]],
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    request_timeout: Optional[int] = None,
) -> str:
    """
    This function completes a chat interaction by aggregating streamed tokens.
    """
    buf: List[str] = []
    async for tok in stream_chat(messages, model=model, temperature=temperature, max_tokens=max_tokens, request_timeout=request_timeout):
        if tok:
            buf.append(tok)
    return "".join(buf)

def embed_texts_sync(
    texts: Sequence[str],
    *,
    model: Optional[str] = None,
    request_timeout: Optional[int] = None,
    batch_size: int = 100,
) -> List[List[float]]:
    """
    This function generates embeddings for a list of texts using the OpenAI API.
    """
    if not texts:
        return []
    timeout = httpx.Timeout(request_timeout or settings.LLM_REQUEST_TIMEOUT)
    used_model = (model or settings.EMBEDDING_MODEL)
    out: List[List[float]] = []
    with httpx.Client(timeout=timeout) as client:
        for i in range(0, len(texts), batch_size):
            chunk = texts[i:i+batch_size]
            r = client.post(_EMB_URL, headers=_headers(), json={"input": list(chunk), "model": used_model})
            r.raise_for_status()
            data = r.json()
            for item in data.get("data", []):
                out.append(item["embedding"])
            time.sleep(0.05)  # To avoid rate limits
    return out

def embed_query_sync(query: str, *, model: Optional[str] = None) -> List[float]:
    """
    This function generates an embedding for a single query string.
    """
    vecs = embed_texts_sync([query], model=model)
    return vecs[0] if vecs else []
