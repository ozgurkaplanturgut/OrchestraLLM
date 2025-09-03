# utils/concurrency.py
import asyncio
from utils.config import settings

LLM_STREAM_SEMAPHORE = asyncio.Semaphore(settings.LLM_MAX_CONCURRENCY)
