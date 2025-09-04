import os
import uuid
from typing import List
from pypdf import PdfReader
from orchestrallm.shared.config.settings import settings

def read_text(file_path: str) -> str:
    """
    This function reads text from a file. It supports PDF and plain text files.
    """
    name = os.path.basename(file_path).lower()
    if name.endswith(".pdf"):
        reader = PdfReader(file_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def chunk_text(text: str, max_chars: int | None = None, overlap: int | None = None) -> List[str]:
    """
    This function splits the input text into chunks of specified maximum character length,
    """
    max_chars = max_chars or settings.RAG_CHUNK_SIZE
    overlap   = overlap   or settings.RAG_CHUNK_OVERLAP
    overlap   = min(overlap, max_chars - 1) if max_chars and max_chars > 1 else 0

    text = text.strip().replace("\r", "")
    chunks: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        j = min(i + max_chars, n)
        chunk = text[i:j]
        chunks.append(chunk)
        if j == n:
            break
        i = max(0, j - overlap)

    return [c.strip() for c in chunks if c and c.strip()]

def make_point_id() -> str:
    """
    This function generates a unique identifier for a data point.
    """
    return str(uuid.uuid4())
