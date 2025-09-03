# app/tasks/travel_tasks.py
"""
Travel task (stream) — Multi-Agent Collaboration + Session Memory.
- Mevcut WS/async mimarisini bozmadan travel akışını güncelledi.
- Writer stream tokenlarını WS'e gönderirken, bitince state persist edilir.
"""

from utils.config import settings
from utils.events import send_token, send_done, send_error, send_status
from app.travel.agno_team import stream_travel_plan


async def run_travel_task(task_id: str, user_id: str, session_id: str, lang: str, query: str):
    """
    This function handles a travel planning task by coordinating multiple agents to research,
    plan, and write a travel itinerary based on user input. It streams the response back to
    the client in real-time.
    """
    if not getattr(settings, "OPENAI_API_KEY", None):
        await send_error(task_id, "OPENAI_API_KEY tanımlı değil.")
        return

    try:
        await send_status(task_id, "[travel] araştırma başlatılıyor")
        await send_status(task_id, "[travel] planlama başlatılıyor")
        await send_status(task_id, "[travel] yazım başlatılıyor (stream)")

        # Writer aşaması stream: token'ları aynen WS'e bas
        async for tok in stream_travel_plan(
            user_id=user_id,
            session_id=session_id,
            query=query,
            language=lang,
            context_id=task_id,  # bu task çalışmasının kimliği olarak da saklıyoruz
        ):
            if tok:
                await send_token(task_id, tok)

    except Exception as e:
        await send_error(task_id, f"Hata: {e}")
        return

    await send_done(task_id)
