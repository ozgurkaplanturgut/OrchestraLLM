from orchestrallm.shared.config.settings import settings
from orchestrallm.shared.eventbus.events import (
    send_token,
    send_done,
    send_error,
    send_status,
)
from orchestrallm.features.travel.app.agno_team import stream_travel_plan


async def run_travel_task(
    task_id: str,
    user_id: str,
    session_id: str,
    query: str,
):
    """
    Handle a travel planning task by coordinating agents.
    Streams tokens to the client in real-time.
    """
    if not getattr(settings, "OPENAI_API_KEY", None):
        await send_error(task_id, "OPENAI_API_KEY tanımlı değil.")
        return

    try:
        await send_status(task_id, "[travel] searching is being initiated")
        await send_status(task_id, "[travel] planning is being initiated")
        await send_status(task_id, "[travel] writing is being initiated")

        async for tok in stream_travel_plan(
            user_id=user_id,
            session_id=session_id,
            query=query,
            context_id=task_id,
        ):
            if tok:
                await send_token(task_id, tok)

    except Exception as e:
        await send_error(task_id, f"Hata: {e}")
        return

    await send_done(task_id)
