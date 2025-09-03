# app/tasks/travel_tasks.py
"""
This module defines a task for handling travel planning using multiple agents to research,
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

        async for tok in stream_travel_plan(
            user_id=user_id,
            session_id=session_id,
            query=query,
            language=lang,
            context_id=task_id,  
        ):
            if tok:
                await send_token(task_id, tok)

    except Exception as e:
        await send_error(task_id, f"Hata: {e}")
        return

    await send_done(task_id)
