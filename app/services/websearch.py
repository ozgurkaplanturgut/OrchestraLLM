# app/services/websearch.py
from __future__ import annotations

from typing import Any, Dict, List, Set
import re
import httpx
from bs4 import BeautifulSoup

try:
    from duckduckgo_search import DDGS  
except Exception:  
    try:
        from ddgs import DDGS  
    except Exception:
        DDGS = None  


def ddg_search(query: str, *, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    This function performs a web search using DuckDuckGo and returns a list of results.
    """
    if DDGS is None:
        return []
    out: List[Dict[str, Any]] = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                href = r.get("href")
                if not href:
                    continue
                out.append({"title": r.get("title", "") or "", "url": href})
    except Exception:
        pass
    return out

def fetch_text(url: str, *, timeout: int = 20) -> str:
    """
    This function fetches and extracts text content from a given URL.
    """
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
            html = r.text
    except Exception:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.extract()
        lines = [ln for ln in soup.get_text("\n", strip=True).splitlines() if ln.strip()]
        return "\n".join(lines[:5000])
    except Exception:
        return ""

def _is_turkish(s: str) -> bool:
    """
    Basit Türkçe tespiti: ç,ğ,ı,ö,ş,ü karakterlerinden biri veya "tarif"/"yemek" kelimeleri.
    """
    ls = s.lower()
    return bool(re.search(r"[çğıöşü]", ls)) or "tarif" in ls or "yemek" in ls

def _expand_queries_minimal(prompt: str) -> List[str]:
    """
    This function expands the input prompt into multiple recipe-related queries.
    """
    base = (prompt or "").strip()
    if not base:
        return []
    queries = [base]
    if _is_turkish(base):
        queries += [f"{base} tarifi", f"{base} tarifleri"]
    # İngilizce varyasyonları da ekle (kaynak çeşitliliği için)
    queries += [f"{base} recipe", f"{base} recipes", f"how to make {base}"]
    seen: Set[str] = set()
    uniq: List[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            uniq.append(q)
    return uniq

def _score_recipe_like(text: str) -> int:
    """
    This function scores the text based on the presence of recipe-like features.
    """
    if not text:
        return 0
    ls = text.lower()
    score = 0
    for w in ("malzemeler", "yapılışı", "hazırlanışı", "tarif", "ingredients", "directions", "instructions", "recipe"):
        if w in ls:
            score += 1
    if re.search(r"(^|\n)[\-•*]\s+\S", text):
        score += 1
    if re.search(r"(^|\n)\d+\.\s+\S", text):
        score += 1
    return score

def _normalize_url(u: str) -> str:
    """
    This function normalizes a URL by stripping fragments and trailing slashes.
    """
    u = (u or "").strip()
    if not u:
        return u
    u = u.split("#")[0]
    if u.endswith("/"):
        u = u[:-1]
    return u

def search_and_extract_recipe(prompt: str, *, max_sources: int = 5) -> Dict[str, Any]:
    """
    This function searches the web for recipe-related content based on the input prompt
    and extracts relevant information from the results.
    """
    results: List[Dict[str, Any]] = []
    seen_urls: Set[str] = set()

    for q in _expand_queries_minimal(prompt):
        hits = ddg_search(q, max_results=6)
        for h in hits:
            url = _normalize_url(h.get("url") or "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            text = fetch_text(url)  
            score = _score_recipe_like(text)

            results.append({
                "title": h.get("title") or "",
                "url": url,
                "text": text,   
                "score": score,
            })

            if len(results) >= max_sources:
                break
        if len(results) >= max_sources:
            break

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"prompt": prompt, "sources": results}


def parse_recipe_from_text(text: str) -> Dict[str, List[str]]:
    """
    Heuristically extract ingredients and steps from plain text.
    Looks for Turkish and English section headers.
    """
    text = text or ""
    if not text.strip():
        return {"ingredients": [], "steps": []}
    ls = text.lower()

    # Section headers
    ing_heads = ["malzemeler", "içindekiler", "ingredients"]
    step_heads = ["yapılışı", "hazırlanışı", "tarif", "adımlar", "instructions", "directions", "method"]

    # Find nearest occurrence
    def find_section(start_words):
        idx = -1
        for w in start_words:
            j = ls.find(w)
            if j != -1:
                if idx == -1 or j < idx:
                    idx = j
        return idx

    i_ing = find_section(ing_heads)
    i_step = find_section(step_heads)

    # Extract blocks
    def block_from(i_start, i_end):
        if i_start == -1:
            return ""
        if i_end != -1 and i_end > i_start:
            return text[i_start:i_end]
        return text[i_start:i_start + 4000]  # cap

    # Determine order and blocks
    if i_ing != -1 and (i_step == -1 or i_ing < i_step):
        ing_block = block_from(i_ing, i_step)
        step_block = block_from(i_step, -1)
    elif i_step != -1:
        ing_block = ""
        step_block = block_from(i_step, -1)
    else:
        ing_block = ""
        step_block = text[:2000]

    # Itemize
    def bulletize(block: str) -> List[str]:
        if not block:
            return []
        lines = [ln.strip(" -*•\t") for ln in block.splitlines()]
        items = []
        for ln in lines:
            if not ln:
                continue
            if re.match(r"^\d+\.", ln):
                items.append(re.sub(r"^\d+\.\s*", "", ln))
            elif re.match(r"^[•\-*]\s+", ln):
                items.append(re.sub(r"^[•\-*]\s*", "", ln))
            elif (len(ln.split()) <= 12 and any(ch.isdigit() for ch in ln)) or any(u in ln.lower() for u in ["gr", "ml", "kaşık", "cup", "tbsp", "tsp"]):
                items.append(ln)
        # Fallback: comma/semicolon split
        if not items:
            tokens = [t.strip() for t in re.split(r",|;|\u2022", block) if t.strip()]
            items = tokens[:12]
        # Deduplicate while preserving order
        seen = set()
        uniq = []
        for it in items:
            if it not in seen:
                uniq.append(it)
                seen.add(it)
        return uniq[:24]

    ingredients = bulletize(ing_block)
    steps = bulletize(step_block)
    # If steps are too short, attempt sentence split
    if steps and all(len(x.split()) <= 5 for x in steps):
        sents = re.split(r"(?<=[.!?])\s+", step_block)
        steps = [s.strip() for s in sents if len(s.strip()) > 6][:10]

    return {"ingredients": ingredients, "steps": steps}
