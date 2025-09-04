from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List

from orchestrallm.features.recipes.infra.recipes_web import search_and_extract_recipe, parse_recipe_from_text
from orchestrallm.shared.llm.openai_client import stream_chat, complete_chat
from orchestrallm.shared.eventbus.events import send_status, send_token, send_error, send_done
from orchestrallm.shared.history import append_message
from orchestrallm.features.recipes.domain.prompts import RECIPE_RECOMMENDER_PROMPT, RECIPE_WRITER_PROMPT

_RE_JSON = re.compile(r'\{(?:[^{}]|\{[^{}]*\})*\}')

def _safe_json_list(s: str) -> List[str]:
    try:
        m = _RE_JSON.search(s)
        if m:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict) and "dishes" in obj and isinstance(obj["dishes"], list):
                return [str(x) for x in obj["dishes"] if isinstance(x, (str, int, float, str))]
    except Exception:
        pass
    parts = [p.strip(" -•*\t ") for p in re.split(r'[\n,]+', s) if p.strip()]
    out: List[str] = []
    for p in parts:
        if len(out) >= 3: break
        if 2 <= len(p) <= 80:
            out.append(p)
    return out[:3]

async def _recommend_dishes(query: str, lang: str) -> List[str]:
    """
    Use LLM to recommend a few dishes based on user query.
    """
    if lang.startswith("tr"):
        user = f"Kullanıcı isteği: {query}\nSadece bir JSON objesi döndür."
    else:
        user = f"User request: {query}\nReturn only one JSON object."

    messages = [
        {"role": "system", "content": RECIPE_RECOMMENDER_PROMPT},
        {"role": "user", "content": user},
    ]
    text = await complete_chat(messages, temperature=0.3, max_tokens=1024)
    return _safe_json_list(text)



def _compose_outline(dishes: List[Dict[str, Any]], lang: str) -> str:
    """
    Create a brief outline of the recommended dishes to send as first response.
    """
    if lang.startswith("tr"):
        lines = ["Öneriler ve özet tarifler:\n"]
        for i, d in enumerate(dishes, 1):
            title = d.get("dish") or d.get("name") or ""
            lines.append(f"{i}. {title}")
            r = d.get("recipe") or {}
            ing = r.get("ingredients") or []
            steps = r.get("steps") or []
            if ing:
                lines.append("  - Malzemeler: " + ", ".join(ing[:8]) + ("..." if len(ing) > 8 else ""))
            if steps:
                lines.append("  - Adımlar: " + "; ".join(steps[:3]) + ("..." if len(steps) > 3 else ""))
            srcs = d.get("sources") or []
            if srcs:
                lines.append("  - Kaynak: " + (srcs[0].get("url") or srcs[0].get("title") or ""))
            lines.append("")
        return "\n".join(lines).strip() + "\n"
    else:
        lines = ["Suggestions and quick outlines:\n"]
        for i, d in enumerate(dishes, 1):
            title = d.get("dish") or d.get("name") or ""
            lines.append(f"{i}. {title}")
            r = d.get("recipe") or {}
            ing = r.get("ingredients") or []
            steps = r.get("steps") or []
            if ing:
                lines.append("  - Ingredients: " + ", ".join(ing[:8]) + ("..." if len(ing) > 8 else ""))
            if steps:
                lines.append("  - Steps: " + "; ".join(steps[:3]) + ("..." if len(steps) > 3 else ""))
            srcs = d.get("sources") or []
            if srcs:
                lines.append("  - Source: " + (srcs[0].get("url") or srcs[0].get("title") or ""))
            lines.append("")
        return "\n".join(lines).strip() + "\n"

async def _stream_story(dishes: List[Dict[str, Any]], lang: str):
    """
    Stream a detailed recipe story from LLM based on collected info.
    """
    user_parts = []
    for d in dishes:
        title = d.get("dish") or d.get("name") or ""
        src = (d.get("sources") or [{}])[0].get("url", "")
        r = d.get("recipe") or {}
        ing = r.get("ingredients") or []
        steps = r.get("steps") or []
        user_parts.append(f"Dish: {title}\nSource: {src}\nIngredients: {ing}\nSteps: {steps}\n")
    user = "\n\n".join(user_parts)
    system_prompt = RECIPE_WRITER_PROMPT + "\n" +  f"USER LANGUAGE: {lang}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user}
    ]
    async for tok in stream_chat(messages, temperature=0.2, max_tokens=2048):
        if tok:
            yield tok

async def run_recipe_task(task_id: str, user_id: str, session_id: str, prompt: str, *, lang: str = "tr"):
    """
    This function handles a recipe generation task by recommending dishes based on user input,
    searching for relevant recipes, and generating a detailed recipe story using LLM.
    It streams the response back to the client in real-time.
    """
    try:
        if lang.startswith("tr"):
            append_message(
                user_id=user_id,
                session_id=session_id,
                role="user",
                content=f"Tarif isteği: {prompt}"
            )
            status_generating = "Öneriler oluşturuluyor..."
            status_collecting = "Kaynaklar toplanıyor..."
            error_prefix = "Hata"
        else:
            append_message(
                user_id=user_id,
                session_id=session_id,
                role="user",
                content=f"Recipe request: {prompt}"
            )
            status_generating = "Generating suggestions..."
            status_collecting = "Collecting sources..."
            error_prefix = "Error"

        await send_status(task_id, status_generating)
        dishes = await _recommend_dishes(prompt, lang)
        if not dishes:
            dishes = [prompt]  # fallback

        await send_status(task_id, status_collecting)
        enriched: List[Dict[str, Any]] = []
        for name in dishes:
            bundle = search_and_extract_recipe(str(name), max_sources=2)
            recipe = {"ingredients": [], "steps": []}
            for s in bundle.get("sources", []):
                if s.get("text"):
                    parsed = parse_recipe_from_text(s["text"])
                    if parsed["ingredients"] or parsed["steps"]:
                        recipe = parsed
                        break
            enriched.append({
                "dish": str(name),
                "sources": bundle.get("sources", []),
                "recipe": recipe
            })

        outline = _compose_outline(enriched, lang)
        for ch in outline:
            await send_token(task_id, ch)
            await asyncio.sleep(0.0005)

        async for tok in _stream_story(enriched, lang):
            await send_token(task_id, tok)

        append_message(user_id=user_id, session_id=session_id, role="assistant", content=outline)

        await send_done(task_id)
    except Exception as e:
        await send_error(task_id, f"{error_prefix}: {e}")


