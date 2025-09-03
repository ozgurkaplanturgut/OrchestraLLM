# utils/config.py
"""
Uygulama yapılandırması (Celery/RabbitMQ YOK).
Pydantic v2 + pydantic-settings.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import logging


class Settings(BaseSettings):
    # Genel
    LOG_LEVEL: str = Field(default="INFO", description="Uygulama log seviyesi")
    BIND: str = Field(default="0.0.0.0:8076", description="API bind adresi")

    # CORS
    CORS_ALLOW_ORIGINS: str = Field(default="*", description="Virgülle ayrık origin listesi")
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True, description="CORS allow credentials")
    CORS_ALLOW_METHODS: str = Field(default="*", description="CORS allow methods")
    CORS_ALLOW_HEADERS: str = Field(default="*", description="CORS allow headers")

    # LLM
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API anahtarı")
    OPENAI_BASE_URL: str = Field(default="https://api.openai.com/v1", description="OpenAI base URL")
    CHAT_MODEL: str = Field(default="gpt-4o-mini", description="Sohbet modeli id")
    EMBEDDING_MODEL: str = Field(default="text-embedding-3-small", description="Embedding modeli id")
    EMBEDDING_DIMENSIONS: int = Field(default=1536)
    MAX_TOKENS: int = Field(default=4096, description="Maksimum token sayısı")
    TEMPERATURE: float = Field(default=0.0, description="Sıcaklık (temperature)")
    LLM_MAX_CONCURRENCY: int = Field(default=10, description="LLM isteklerinde maksimum eşzamanlılık")
    LLM_REQUEST_TIMEOUT: int = Field(default=60, description="LLM HTTP timeout (s)")

    # Veri Katmanı
    MONGODB_URI: str = Field(
        default="mongodb://mongo:27017/ragchat",
        description="MongoDB bağlantı URI",
        validation_alias="MONGO_URI",
    )
    MONGODB_DB: str = Field(
        default="ragchat",
        description="MongoDB veritabanı adı",
        validation_alias="MONGO_DB",
    )
    QDRANT_URL: str = Field(default="http://qdrant:6333", description="Qdrant HTTP URL")
    QDRANT_COLLECTION: str = Field(default="rag_docs", description="Qdrant koleksiyon adı")

    # RAG ayarları
    RAG_TOPK: int = Field(default=5, description="İlk getirilecek döküman adedi")
    RAG_RERANK_MODE: str = Field(default="none", description="none|local|api")
    RAG_CHUNK_SIZE: int = Field(default=750, description="Chunk boyutu (karakter)")
    RAG_CHUNK_OVERLAP: int = Field(default=100, description="Chunk overlap (karakter)")

    # Sohbet geçmişi
    HISTORY_MAX_TURNS: int = Field(default=20, description="Bir konuşmada tutulacak maksimum geçmiş tur sayısı")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()


def init_logging() -> None:
    lvl = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(level=lvl, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    # Gürültülü loggerları kıs
    for noisy in ("httpx", "pymongo", "qdrant", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)