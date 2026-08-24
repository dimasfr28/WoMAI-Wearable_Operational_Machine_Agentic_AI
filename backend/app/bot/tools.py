from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.bot.retriever import search_bot_sensor_data
from app.db.models import Document, Machine, SensorRun

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool Function Definitions
# ---------------------------------------------------------------------------


def search_sensor_data(
    query: str,
    machine_id: str | None = None,
    k: int = 5,
) -> list[dict[str, Any]]:
    """Search sensor summaries and chunk data semantically from ChromaDB bot_sensor_data collection."""
    return search_bot_sensor_data(query_text=query, machine_id=machine_id, k=k)


def list_machines_tool(db: Session) -> list[dict[str, Any]]:
    """Retrieve the list of all registered machines in the database."""
    machines = db.query(Machine).order_by(Machine.created_at.asc()).all()
    results = []
    for m in machines:
        results.append({
            "id": str(m.id),
            "name": m.name,
            "machine_type": m.machine_type,
            "status": m.status,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })
    return results


list_machines = list_machines_tool


def get_machine_info_tool(db: Session, machine_id: str) -> dict[str, Any] | None:
    """Retrieve detailed machine info including associated document and sensor run counts."""
    if not machine_id:
        return None

    try:
        m_uuid = uuid.UUID(str(machine_id).strip())
    except (ValueError, TypeError, AttributeError):
        return None

    machine = db.query(Machine).filter(Machine.id == m_uuid).first()
    if machine is None:
        return None

    doc_count = db.query(Document).filter(Document.machine_id == machine.id).count()
    run_count = db.query(SensorRun).filter(SensorRun.machine_id == machine.id).count()

    return {
        "id": str(machine.id),
        "name": machine.name,
        "machine_type": machine.machine_type,
        "status": machine.status,
        "document_count": doc_count,
        "sensor_run_count": run_count,
        "created_at": machine.created_at.isoformat() if machine.created_at else None,
    }


get_machine_info = get_machine_info_tool


# ---------------------------------------------------------------------------
# Tool Schemas / Metadata for Agent LLM Prompts
# ---------------------------------------------------------------------------

BOT_TOOL_DEFINITIONS = [
    {
        "name": "search_sensor_data",
        "description": "Cari data sensor dan ringkasan kondisi mesin secara semantik dari database vektor.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Query pencarian semantik (misal: 'suhu tinggi', 'kecepatan putar rpm drop', 'tool wear aus')",
                },
                "machine_id": {
                    "type": "string",
                    "description": "UUID mesin opsional untuk memfilter pencarian ke mesin tertentu",
                },
                "k": {
                    "type": "integer",
                    "description": "Jumlah hasil pencarian relevan yang ingin diambil (default 5)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_machines",
        "description": "Daftar semua mesin CNC dan milling yang terdaftar beserta status operasional dan informasinya.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_machine_info",
        "description": "Ambil informasi detail mesin tertentu berdasarkan ID mesin (UUID), termasuk jumlah dokumen manual dan data run sensor.",
        "parameters": {
            "type": "object",
            "properties": {
                "machine_id": {
                    "type": "string",
                    "description": "UUID dari mesin yang ingin dicari informasinya",
                },
            },
            "required": ["machine_id"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool Dispatcher
# ---------------------------------------------------------------------------


def execute_bot_tool(tool_name: str, args: dict[str, Any] | None, db: Session) -> str:
    """Execute a bot agent tool by name with arguments and database session, returning JSON string."""
    if args is None:
        args = {}

    norm_name = tool_name.strip().lower()

    try:
        if norm_name in ("search_sensor_data", "search_bot_sensor_data"):
            query = args.get("query") or args.get("query_text") or ""
            machine_id = args.get("machine_id")
            k = int(args.get("k", 5)) if args.get("k") is not None else 5
            res = search_sensor_data(query=str(query), machine_id=str(machine_id) if machine_id else None, k=k)
            return json.dumps(res, default=str, ensure_ascii=False)

        elif norm_name in ("list_machines", "list_machines_tool"):
            res = list_machines_tool(db=db)
            return json.dumps(res, default=str, ensure_ascii=False)

        elif norm_name in ("get_machine_info", "get_machine_info_tool"):
            machine_id = args.get("machine_id")
            if not machine_id:
                return json.dumps({"error": "Argument 'machine_id' is required for get_machine_info."}, ensure_ascii=False)
            res = get_machine_info_tool(db=db, machine_id=str(machine_id))
            if res is None:
                return json.dumps({"error": f"Machine with ID '{machine_id}' not found."}, ensure_ascii=False)
            return json.dumps(res, default=str, ensure_ascii=False)

        else:
            return json.dumps({"error": f"Unknown tool '{tool_name}'."}, ensure_ascii=False)

    except Exception as exc:
        logger.exception("execute_bot_tool failed for tool '%s'", tool_name)
        return json.dumps({"error": f"Tool execution failed: {str(exc)}"}, ensure_ascii=False)
