from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_auth import router as auth_router
from app.api.routes_knowledgebase import router as knowledgebase_router
from app.api.routes_machine import router as machine_router
from app.api.routes_report import router as report_router
from app.api.routes_sensor import router as sensor_router

app = FastAPI(title="Predictive Maintenance Copilot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(machine_router)
app.include_router(knowledgebase_router)
app.include_router(sensor_router)
app.include_router(report_router)


@app.get("/health")
def health():
    return {"status": "ok"}
