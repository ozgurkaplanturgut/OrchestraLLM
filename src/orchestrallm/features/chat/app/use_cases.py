# tasks/chat_tasks.py
"""
This module handles chat tasks by managing conversation history and interacting with the OpenAI API.
It streams responses back to the client in real-time.
"""
import logging
from typing import List, Dict

import httpx
from orchestrallm.shared.config.settings import settings
from orchestrallm.shared.eventbus.events import send_token, send_error, send_done, send_status
from orchestrallm.shared.history import load_history, append_message  # alias ile eski isim de çalışır
from orchestrallm.shared.llm.openai_client import stream_chat

from orchestrallm.features.chat.domain.prompts import BASIC_CHATBOT_PROMPT

# Logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger("api")


async def run_chat_task(task_id: str, user_id: str, session_id: str, query: str):
    """
    This function handles a chat task by managing the conversation history and interacting with the OpenAI API.
    It streams the response back to the client in real-time.
    """
    if not settings.OPENAI_API_KEY:
        await send_error(task_id, "OPENAI_API_KEY tanımlı değil.")
        return

    try:
        # 1) Geçmişi al
        await send_status(task_id, "Geçmiş yükleniyor...")
        history_limit = getattr(settings, "HISTORY_MAX_TURNS", 10) or 10
        recent = load_history(user_id=user_id, session_id=session_id, limit=history_limit)

        # 2) Kullanıcı mesajını geçmişe yaz
        try:
            append_message(user_id=user_id, session_id=session_id, role="user", content=query)
        except Exception as e:
            logger.warning(f"history append (user) failed: {e}")

        # 3) Mesajları hazırla (system opsiyonel)
        messages: List[Dict[str, str]] = [{"role": "system", "content": BASIC_CHATBOT_PROMPT}]
        for m in recent or []:
            role = m.get("role")
            content = m.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": query})

        # 4) Stream cevap + biriktir
        await send_status(task_id, "Yanıt oluşturuluyor...")
        final_chunks: List[str] = []
        async for tok in stream_chat(messages):
            final_chunks.append(tok)
            await send_token(task_id, tok)
        final_text = "".join(final_chunks).strip()

        # 5) Asistan cevabını geçmişe yaz
        try:
            append_message(user_id=user_id, session_id=session_id, role="assistant", content=final_text)
        except Exception as e:
            logger.warning(f"history append (assistant) failed: {e}")

        await send_done(task_id)

    except httpx.HTTPError as e:
        await send_error(task_id, f"OpenAI HTTP hatası: {e}")
    except Exception as e:
        logger.exception("Chat task error")
        await send_error(task_id, f"Chat hata: {e}")
