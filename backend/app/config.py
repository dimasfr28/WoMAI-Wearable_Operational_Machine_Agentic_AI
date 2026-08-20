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
    CHROMA_COLLECTION_BOT_SENSOR: str = "bot_sensor_data"

    # --- Embedding ---
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    EMBEDDING_SERVICE_URL: str = "http://embedding-service:8000"

    # --- MinerU (PDF -> Markdown parsing service) ---
    MINERU_SERVICE_URL: str = "http://mineru-service:8000"

    # --- Groq LLM (kept installed/importable as a fallback reference —
    # app.llm.groq_client is no longer imported by any call site; see
    # app.llm.gemini_client, the active provider) ---
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # --- Gemini LLM (active provider) ---
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.1-flash-lite"

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
    # NOT /app/reports: /app is bind-mounted from the host in dev (dev.compose.yaml)
    # and watched by uvicorn --reload — every generated Machine Report PDF landing
    # there triggered a full app reload (regenerating JWT_SECRET mid-session, see
    # get_settings(), and interrupting whatever request was in flight). /data/reports
    # sits outside the watched tree, same convention as PDF_LIBRARY_DIR below.
    REPORTS_DIR: str = "/data/reports"

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

    # --- Telegram notifications (optional — no-op if either is empty, see
    # app/notifications/telegram.py) ---
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # --- Sensor run clustering (assign_run_id, routes_sensor.py) ---
    # Tolerance between two consecutive readings' elapsed wall-clock time and
    # their tool_wear_min delta for them to still count as the same run —
    # generous relative to the ESP32's ~60s submit interval so normal
    # jitter/batching never false-splits a run, while a genuinely stale or
    # replayed reading (minutes-to-hours of mismatch) still does.
    RUN_SYNC_TOLERANCE_MINUTES: float = 10.0
    # Hard cap on same-run continuation, independent of the sync-tolerance
    # check above — a fixed-cadence data source (e.g. SimulationManager,
    # routes_sensor.py) can keep tool_wear perfectly in sync with elapsed
    # time indefinitely, which would otherwise never trip the sync check and
    # let a single run run forever. TEMPORARY: set low (2 min) for demoing
    # the simulation feature with a fresh run/report every cycle; revisit
    # once real ESP32 cadence/tuning is settled.
    RUN_MAX_SAME_RUN_GAP_MINUTES: float = 2.0

    # --- Simulation auto-start (SimulationManager, routes_sensor.py) ---
    # Delay after backend startup before auto-starting demo simulation for
    # every existing machine — SimulationManager's state is in-memory only,
    # so a process restart otherwise leaves it dormant until some reading
    # arrives via submit_reading() to re-trigger it.
    SIMULATION_AUTOSTART_DELAY_SECONDS: float = 120.0


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
