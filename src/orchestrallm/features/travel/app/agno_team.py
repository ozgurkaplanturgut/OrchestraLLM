from __future__ import annotations
import json
from typing import AsyncGenerator, Dict, List

from orchestrallm.shared.llm.openai_client import stream_chat
from orchestrallm.shared.websearch.ddg import ddg_search
from orchestrallm.features.travel.infra.memory import load_last_state, save_travel_state
from orchestrallm.features.travel.domain.prompts import (TRAVEL_PLANNER_SYSTEM_PROMPT, 
                           TRAVEL_SEARCHER_SYSTEM_PROMPT,  
                           TRAVEL_WRITER_SYSTEM_PROMPT)

def _as_str(x) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    try:
        return json.dumps(x, ensure_ascii=False)
    except Exception:
        return str(x)

async def _collect_stream(messages: List[Dict], temperature: float = 0.2) -> str:
    """
    Collect streamed tokens into a single string.
    """
    buf: List[str] = []
    async for tok in stream_chat(messages, temperature=temperature, max_tokens=4096):
        if tok:
            buf.append(tok)
    return "".join(buf).strip()

def _mk_msgs(system_text: str, user_text: str) -> List[Dict[str, str]]:
    """
    Create message list for chat API.
    """
    msgs: List[Dict[str, str]] = []
    st = (system_text or "").strip()
    if st:
        msgs.append({"role": "system", "content": st})
    msgs.append({"role": "user", "content": user_text})
    return msgs

async def stream_travel_plan(
    user_id: str,
    session_id: str,
    query: str,
    context_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    This function coordinates multiple agents to research, plan, and write a travel itinerary.
    It streams the final written itinerary back as tokens.
    """
    last_state = load_last_state(user_id=user_id, session_id=session_id) or {}
    current_plan_text = last_state.get("plan_text", "") or ""
    current_final_text = last_state.get("final_text", "") or ""
    has_current = bool(current_plan_text or current_final_text)

    results = ddg_search(query, max_results=6)
    search_json = json.dumps(results, ensure_ascii=False, indent=2)

    # --- Researcher ---
    researcher_user = _as_str(
        f"USER DEMAND: {query}\n\n"
        f"[CURRENT PLAN]\n{current_plan_text if has_current else '(yok)'}\n\n"
        f"[SEARCH RESULTS]\n{search_json}"
    )
    research_text = await _collect_stream(_mk_msgs(TRAVEL_SEARCHER_SYSTEM_PROMPT, researcher_user), temperature=0.1)

    # --- Planner ---
    planner_user = _as_str(
        f"USER DEMAND: {query}\n\n"
        f"[CURRENT PLAN]\n{current_plan_text if has_current else '(yok)'}\n\n"
        f"[SEARCH RESULTS]\n{research_text}"
    )
    plan_text = await _collect_stream(_mk_msgs(TRAVEL_PLANNER_SYSTEM_PROMPT, planner_user), temperature=0.2)

    writer_user = _as_str(
        f"USER DEMAND: {query}\n\n"
        f"[CURRENT PLAN]\n{current_plan_text if has_current else '(yok)'}\n\n"
        f"[NEW PLAN EXAMPLE]\n{plan_text}\n\n"
        f"[DETAILED RESEARCH RESULT]\n{research_text}"
        f"[IMPORTANT NOTE: Always respond in the same language as the USER DEMAND.]"
    )

    final_buf: List[str] = []
    async for tok in stream_chat(_mk_msgs(TRAVEL_WRITER_SYSTEM_PROMPT, writer_user), temperature=0.15, max_tokens=4096):
        if tok:
            final_buf.append(tok)
            yield tok
    final_text = "".join(final_buf).strip()


    save_travel_state(
        user_id=user_id,
        session_id=session_id,
        payload={"research_text": research_text, "plan_text": plan_text, "final_text": final_text, "query": query},
    )
