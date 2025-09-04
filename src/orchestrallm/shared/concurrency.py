import asyncio
from orchestrallm.shared.config.settings import settings

LLM_STREAM_SEMAPHORE = asyncio.Semaphore(settings.LLM_MAX_CONCURRENCY)
