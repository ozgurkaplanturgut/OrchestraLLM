from __future__ import annotations
import httpx
from bs4 import BeautifulSoup

def fetch_text(url: str, *, timeout: int = 20) -> str:
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
