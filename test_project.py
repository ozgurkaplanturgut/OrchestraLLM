"""
End-to-end test script for the async API:
- Chat (basic, memory in Mongo) with streaming
- Ingest (download->chunk->embed->Qdrant)
- RAG query over ingested doc with streaming
- Travel planning (agno team) with streaming

Requires:
  pip install requests websockets

Default base_url: http://127.0.0.1:8076
"""
import argparse
import asyncio
import json
import sys
import time
import uuid
from typing import Any, Dict, List
from urllib.parse import urlparse

import requests
import websockets


def _pp(title: str, obj: Any):
    print(f"\n===== {title} =====")
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def _post(base_url: str, path: str, payload: Dict[str, Any], timeout: int = 30) -> requests.Response:
    url = f"{base_url.rstrip('/')}{path}"
    return requests.post(url, json=payload, timeout=timeout)


def _get(base_url: str, path: str, timeout: int = 30) -> requests.Response:
    url = f"{base_url.rstrip('/')}{path}"
    return requests.get(url, timeout=timeout)


def _ws_url_from_base(base_url: str) -> str:
    """
    http://127.0.0.1:8076 -> ws://127.0.0.1:8076
    https://x.y -> wss://x.y
    """
    p = urlparse(base_url)
    if p.scheme == "https":
        scheme = "wss"
    else:
        scheme = "ws"
    netloc = p.netloc or p.path  # handle cases where only host:port is passed
    return f"{scheme}://{netloc}"


async def _stream_task(base_url: str, task_id: str, *, since: int = 0, timeout: int = 180, print_tokens: bool = True) -> Dict[str, Any]:
    """
    Connects to /v1/stream/{task_id}?since=<since> and listens until 'done' or 'error'.
    Returns dict with 'events' list and 'final_text' (joined tokens).
    """
    ws_base = _ws_url_from_base(base_url)
    uri = f"{ws_base}/v1/stream/{task_id}?since={since}"

    tokens: List[str] = []
    events: List[Dict[str, Any]] = []
    done = False
    err = None

    async def _recv_forever():
        nonlocal done, err
        start = time.time()
        async with websockets.connect(uri, ping_interval=None) as ws:
            while not done and (time.time() - start) < timeout:
                msg = await ws.recv()

                # Try parse JSON; text events (like "pong") may come
                try:
                    data = json.loads(msg)
                except Exception:
                    # raw text like "pong"
                    continue

                events.append(data)

                typ = data.get("type")
                if typ == "token":
                    tok = data.get("content", "")
                    if tok and print_tokens:
                        # stream to terminal
                        sys.stdout.write(tok)
                        sys.stdout.flush()
                    tokens.append(tok)
                elif typ == "done":
                    done = True
                    break
                elif typ == "error":
                    # bazı yerlerde 'message', bazılarında 'content' kullanılıyor
                    err = data.get("message") or data.get("content") or json.dumps(data, ensure_ascii=False)
                    # hata text'ini ekrana da bas ki logsuz ortamda görebilelim
                    sys.stdout.write(f"\n[ERROR] {err}\n")
                    sys.stdout.flush()
                    break

    await _recv_forever()
    if print_tokens:
        print()  # newline after stream

    return {
        "ok": (err is None),
        "error": err,
        "events": events,
        "final_text": "".join(tokens),
    }


def test_health(base_url: str):
    r = _get(base_url, "/health")
    _pp("Health", {"status_code": r.status_code, "response": r.json()})


async def test_chat_sequence(base_url: str, user: str, session: str):
    print("\n############################")
    print("# TEST 1: CHAT (stream)")
    print("######################")

    q1 = "Benim adım ?"
    r1 = _post(base_url, "/v1/tasks/chat", {"user_id": user, "session_id": session, "query": q1})
    task1 = r1.json()["task_id"]
    res1 = await _stream_task(base_url, task1, timeout=120)

    q2 = "Benim adım Özgür."
    r2 = _post(base_url, "/v1/tasks/chat", {"user_id": user, "session_id": session, "query": q2})
    task2 = r2.json()["task_id"]
    res2 = await _stream_task(base_url, task2, timeout=120)

    q3 = "Bana Fenerbahçe hakkında 2 cümle söyle"
    r3 = _post(base_url, "/v1/tasks/chat", {"user_id": user, "session_id": session, "query": q3})
    task3 = r3.json()["task_id"]
    res3 = await _stream_task(base_url, task3, timeout=120)

    q4 = "Bana rastgele 250 kelimelik bir hikaye anlat"
    r4 = _post(base_url, "/v1/tasks/chat", {"user_id": user, "session_id": session, "query": q4})
    task4 = r4.json()["task_id"]
    res4 = await _stream_task(base_url, task4, timeout=120)

    q4 = "Benim adım neydi?"
    r4 = _post(base_url, "/v1/tasks/chat", {"user_id": user, "session_id": session, "query": q4})
    task4 = r4.json()["task_id"]
    res4 = await _stream_task(base_url, task4, timeout=120)


async def test_ingest_and_rag(base_url: str, user: str, session: str, doc_url: str, doc_id: str, rag_questions: List[str]):
    print("\n############################")
    print("# TEST 2: INGEST DOCUMENT (stream status) + RAG QUERIES (stream)")
    print("######################")

    # Ingest
    r = _post(base_url, "/v1/tasks/ingest", {
        "user_id": user,
        "session_id": session,
        "document_url": doc_url,
        "document_id": doc_id,
    }, timeout=120)
    _pp("Enqueue Ingest", {"status_code": r.status_code, "response": r.json()})
    ingest_task = r.json()["task_id"]

    print("\n--- Ingest stream ---")
    ingest_res = await _stream_task(base_url, ingest_task, timeout=240, print_tokens=False)
    _pp("Ingest Result", {"ok": ingest_res["ok"], "error": ingest_res["error"]})

    # RAG questions
    for i, q in enumerate(rag_questions, start=1):
        print(f"\n--- RAG #{i} ---")
        rrag = _post(base_url, "/v1/tasks/rag", {
            "user_id": user,
            "session_id": session,
            "query": q,
            "related_document_id": doc_id,
            "mode": "simple",
        })
        task = rrag.json()["task_id"]
        res = await _stream_task(base_url, task, timeout=180)


async def test_travel(base_url: str, user: str, session: str, travel_questions: List[str], timeout_s: int = 600):
    print("\n############################")
    print("# TEST 4: TRAVEL (Multi-Agent)")
    print("######################")

    for q in travel_questions:
        r = _post(base_url, "/v1/tasks/travel", {"user_id": user, "session_id": session, "query": q, "lang": "tr"})
        task = r.json()["task_id"]
        res = await _stream_task(base_url, task, timeout=timeout_s)

async def test_recipes(base_url: str, user: str, session: str, prompt: str = "Bana kıyma ile yapılabilecek bir yemek öner", lang: str = "tr"):
    print("\n############################")
    print("# TEST 3: AUTOGEN RECIPES (stream)")
    print("############################\n")
    r = _post(base_url, "/v1/tasks/recipes", {"user_id": user, "session_id": session, "query": prompt, "lang": lang})
    task_id = r.json()["task_id"]
    res = await _stream_task(base_url, task_id, timeout=240)


# ==============================
# main
# ==============================

def main():
    parser = argparse.ArgumentParser(description="Async RAG & Chat & Travel test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8076", help="API base URL")
    parser.add_argument("--user", default="user_ozgur_11")
    parser.add_argument("--session", default="user_ozgur_1_session_aaaaa1aaa1aa11")
    parser.add_argument("--doc-url", default="https://unec.edu.az/application/uploads/2014/12/pdf-sample.pdf", help="Public/hosted URL reachable from API container")
    parser.add_argument("--doc-id", default=f"doc-{uuid.uuid4().hex[:8]}")
    parser.add_argument("--travel-timeout", type=int, default=600)
    args = parser.parse_args()

    # 0) Health
    test_health(args.base_url)

    # #1) Chat sequence (remembering name)
    # asyncio.run(test_chat_sequence(args.base_url, args.user, args.session))

    # # 2) Ingest + RAG
    # rag_qs = [
    #     "what is my name",
    #     "my name is özgür",
    #     "by whom can adobe be distributed from?",
    #     "what is my name"
    # ]
    # asyncio.run(test_ingest_and_rag(args.base_url, args.user, args.session, args.doc_url, args.doc_id, rag_qs))

    # #3) Recipe
    # asyncio.run(test_recipes(args.base_url, args.user, args.session))

    # 4) Travel
    travel_qs = [
        "make me a travel plan to germany for a low budget"
    ]
    asyncio.run(test_travel(args.base_url, args.user, args.session, travel_qs, timeout_s=args.travel_timeout))


if __name__ == "__main__":
    main()
