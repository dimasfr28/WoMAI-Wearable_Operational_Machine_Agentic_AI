"""Application configuration loaded from environment variables (.env)."""
import secrets
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

    # --- Embedding ---
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    EMBEDDING_SERVICE_URL: str = "http://embedding-service:8000"

    # --- MinerU (PDF -> Markdown parsing service) ---
    MINERU_SERVICE_URL: str = "http://mineru-service:8000"

    # --- Groq LLM ---
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # --- Model ML ---
    # Klasifikasi biner "gagal sekarang" (rancangan.txt Section 5, "Failure
    # Clasification") — XGBoost·rec, 9 fitur. Menggantikan model RandomForest
    # lama (best_model.pkl, dihapus).
    ML_CLASIFICATION_MODEL_PATH: str = "/app/saved/clasification/clasification_model.pkl"
    # "akan gagal dalam 10 menit ke depan?" (rancangan.txt Section 5,
    # "Probability Failure in +10 Minute") — model terpisah, 4 fitur mentah.
    ML_HORIZON_MODEL_PATH: str = "/app/saved/horizon/horizon_model.pkl"

    # --- PDF library (uploaded + pre-existing manuals persisted to disk) ---
    PDF_LIBRARY_DIR: str = "/data/pdf_library"

    # --- Machine Report PDF (rancangan.txt Section 7) ---
    REPORTS_DIR: str = "/app/reports"

    # --- SearXNG ---
    SEARXNG_BASE_URL: str = "http://searxng:8080"

    # --- Duplicate check thresholds ---
    DUPLICATE_CHUNK_SIMILARITY_THRESHOLD: float = 0.93
    DUPLICATE_CHUNK_RATIO_THRESHOLD: float = 0.85

    # --- JWT ---
    # Sengaja BUKAN dibaca dari .env — di-generate ulang secara acak setiap
    # kali proses backend start (lihat get_settings() di bawah), supaya semua
    # token JWT yang diterbitkan sebelum restart otomatis gagal verifikasi
    # signature begitu backend restart (docker compose restart/up ulang, dst.)
    # dan setiap sesi browser dipaksa logout — bukan tersimpan valid sampai
    # JWT_EXPIRE_MINUTES habis seperti sebelumnya. Nilai default di sini
    # ("changeme") tidak pernah benar-benar dipakai; overridden di
    # get_settings().
    JWT_SECRET: str = "changeme"
    JWT_EXPIRE_MINUTES: int = 1440
    JWT_ALGORITHM: str = "HS256"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # secrets.token_urlsafe, bukan .env — baru di setiap proses start, jadi
    # semua token JWT lama invalid setelah restart (lihat komentar JWT_SECRET
    # di atas). @lru_cache memastikan ini hanya dipanggil sekali per proses,
    # jadi nilainya stabil selama proses backend itu hidup (encode/decode
    # tetap konsisten dalam satu masa hidup container).
    settings.JWT_SECRET = secrets.token_urlsafe(32)
    return settings


settings = get_settings()
