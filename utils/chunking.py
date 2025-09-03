# utils/chunking.py
from __future__ import annotations
from typing import List

def chunk_text(text: str, *, max_chars: int = 1500, overlap: int = 150) -> List[str]:
    text = text or ""
    if not text.strip():
        return []
    out: List[str] = []
    i, n = 0, len(text)
    while i < n:
        j = min(i + max_chars, n)
        chunk = text[i:j].strip()
        if chunk:
            out.append(chunk)
        if j == n:
            break
        i = max(0, j - overlap)
    return out
