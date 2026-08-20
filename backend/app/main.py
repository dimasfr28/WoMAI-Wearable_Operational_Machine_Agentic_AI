import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_auth import router as auth_router
from app.api.routes_bot import router as bot_router
from app.api.routes_chat import router as chat_router
from app.api.routes_knowledgebase import router as knowledgebase_router
from app.api.routes_machine import router as machine_router
from app.api.routes_machine_report import router as machine_report_router
from app.api.routes_report import router as report_router
from app.api.routes_sensor import SimulationManager
from app.api.routes_sensor import router as sensor_router
from app.api.routes_sop import router as sop_router
from app.config import settings
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


async def _auto_start_simulations() -> None:
    """SimulationManager's state is in-memory only, so it goes dormant on
    every process (re)start until some reading arrives via submit_reading()
    to re-trigger it — wait SIMULATION_AUTOSTART_DELAY_SECONDS then start it
    for every existing machine instead, so a fresh process resumes producing
    demo data on its own."""
    await asyncio.sleep(settings.SIMULATION_AUTOSTART_DELAY_SECONDS)
    db = SessionLocal()
    try:
        count = SimulationManager.start_all(db)
        logger.info("Auto-started simulation for %d machine(s) after startup delay", count)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_auto_start_simulations())
    yield
    task.cancel()


app = FastAPI(title="Predictive Maintenance Copilot API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(bot_router)
app.include_router(machine_router)
app.include_router(knowledgebase_router)
app.include_router(sensor_router)
app.include_router(report_router)
app.include_router(machine_report_router)
app.include_router(sop_router)
app.include_router(chat_router)


@app.get("/health")
def health():
    return {"status": "ok"}
