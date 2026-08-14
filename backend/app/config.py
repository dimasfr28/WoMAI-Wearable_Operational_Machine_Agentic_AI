"""Application configuration loaded from environment variables (.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Database ---
    POSTGRES_USER: str = "comfest"
    POSTGRES_PASSWORD: str = "changeme"
    POSTGRES_DB: str = "comfest_db"
    DATABASE_URL: str = "postgresql+psycopg://comfest:changeme@postgres:5432/comfest_db"

    # --- ChromaDB ---
    CHROMA_HOST: str = "chromadb"
    CHROMA_PORT: int = 8000
    CHROMA_COLLECTION_DOCS: str = "knowledgebase_docs"
    CHROMA_COLLECTION_SENSOR: str = "knowledgebase_sensor_runs"
    CHROMA_COLLECTION_BOT_SENSOR: str = "bot_sensor_data"

    # --- Embedding ---
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    # --- Groq LLM ---
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # --- Model ML ---
    ML_MODEL_PATH: str = "/app/saved/best_model.pkl"
    ML_PERFORMANCE_LOG_PATH: str = "/app/saved/best_performance_log.json"

    # --- PDF library (uploaded + pre-existing manuals persisted to disk) ---
    PDF_LIBRARY_DIR: str = "/data/pdf_library"

    # --- SearXNG ---
    SEARXNG_BASE_URL: str = "http://searxng:8080"

    # --- Duplicate check thresholds ---
    DUPLICATE_CHUNK_SIMILARITY_THRESHOLD: float = 0.93
    DUPLICATE_CHUNK_RATIO_THRESHOLD: float = 0.85

    # --- JWT ---
    JWT_SECRET: str = "changeme"
    JWT_EXPIRE_MINUTES: int = 1440
    JWT_ALGORITHM: str = "HS256"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
