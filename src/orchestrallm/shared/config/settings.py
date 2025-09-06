from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import logging


class Settings(BaseSettings):
    # General
    LOG_LEVEL: str = Field(default="INFO", description="Application log level")
    BIND: str = Field(default="0.0.0.0:8076", description="API bind address")

    # CORS
    CORS_ALLOW_ORIGINS: str = Field(default="*", description="Comma-separated list of allowed origins")
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True, description="Allow credentials in CORS")
    CORS_ALLOW_METHODS: str = Field(default="*", description="Allowed CORS methods")
    CORS_ALLOW_HEADERS: str = Field(default="*", description="Allowed CORS headers")

    # LLM
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key")
    OPENAI_BASE_URL: str = Field(default="https://api.openai.com/v1", description="OpenAI base URL")
    CHAT_MODEL: str = Field(default="gpt-4o-mini", description="Chat model ID")
    EMBEDDING_MODEL: str = Field(default="text-embedding-3-small", description="Embedding model ID")
    EMBEDDING_DIMENSIONS: int = Field(default=1536)
    MAX_TOKENS: int = Field(default=4096, description="Maximum token count")
    TEMPERATURE: float = Field(default=0.0, description="Temperature")
    LLM_MAX_CONCURRENCY: int = Field(default=10, description="Maximum concurrency for LLM requests")
    LLM_REQUEST_TIMEOUT: int = Field(default=60, description="LLM HTTP timeout (seconds)")

    # Data Layer
    MONGODB_URI: str = Field(
        default="mongodb://mongo:27017/ragchat",
        description="MongoDB connection URI",
        validation_alias="MONGO_URI",
    )
    MONGODB_DB: str = Field(
        default="ragchat",
        description="MongoDB database name",
        validation_alias="MONGO_DB",
    )
    QDRANT_URL: str = Field(default="http://qdrant:6333", description="Qdrant HTTP URL")
    QDRANT_COLLECTION: str = Field(default="rag_docs", description="Qdrant collection name")

    # RAG settings
    RAG_TOPK: int = Field(default=5, description="Number of documents to retrieve")
    RAG_RERANK_MODE: str = Field(default="none", description="Rerank mode: none | local | api")
    RAG_CHUNK_SIZE: int = Field(default=750, description="Chunk size (characters)")
    RAG_CHUNK_OVERLAP: int = Field(default=100, description="Chunk overlap (characters)")

    # Chat history
    HISTORY_MAX_TURNS: int = Field(default=20, description="Maximum number of turns stored in conversation history")

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
    # Reduce verbosity of noisy loggers
    for noisy in ("httpx", "pymongo", "qdrant", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
