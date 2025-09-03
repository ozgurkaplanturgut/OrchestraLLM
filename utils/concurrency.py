# utils/concurrency.py
import asyncio
from utils.config import settings

# OpenAI çağrıları için global semafor
LLM_STREAM_SEMAPHORE = asyncio.Semaphore(settings.LLM_MAX_CONCURRENCY)
