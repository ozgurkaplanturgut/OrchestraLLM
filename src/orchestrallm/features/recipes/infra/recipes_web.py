from __future__ import annotations
from typing import Any, Dict, List, Set
from orchestrallm.shared.websearch.ddg import ddg_search
from orchestrallm.shared.web.fetch import fetch_text

def _is_turkish(s: str) -> bool:
    ls = s.lower()
    return any(ch in ls for ch in "çğıöşü") or "tarif" in ls or "yemek" in ls

def _expand_queries_minimal(prompt: str) -> List[str]:
    base = (prompt or "").strip()
    if not base: return []
    qs = [base]
    qs += [base + (" tarif" if _is_turkish(base) else " recipe")]
    return list(dict.fromkeys(qs))

def search_and_extract_recipe(prompt: str, *, max_sources: int = 5) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for q in _expand_queries_minimal(prompt):
        for r in ddg_search(q, max_results=6):
            url = (r.get("url") or "").split("#", 1)[0]
            if not url or url in seen: 
                continue
            seen.add(url)
            text = fetch_text(url, timeout=15)
            score = sum(k in (text or "").lower() for k in ["ingredients","malzemeler","instructions","hazırlanışı"])
            results.append({"query": q, "title": r.get("title"), "url": url, "snippet": r.get("snippet"), "score": score})
            if len(results) >= max_sources:
                break
        if len(results) >= max_sources:
            break
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"prompt": prompt, "sources": results}

def parse_recipe_from_text(text: str) -> Dict[str, List[str]]:
    t = (text or "").strip()
    if not t: 
        return {"ingredients": [], "steps": []}
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    ing = [ln for ln in lines if any(k in ln.lower() for k in ["gr","ml","cup","tbsp","tsp","adet","malzeme"])]
    steps = [ln for ln in lines if ln not in ing]
    return {"ingredients": ing[:30], "steps": steps[:40]}
