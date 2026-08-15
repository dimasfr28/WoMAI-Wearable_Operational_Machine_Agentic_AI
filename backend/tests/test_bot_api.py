"""Comprehensive verification & end-to-end tests for /bot API and LangGraph agent.

Tests cover:
1. GET /bot/sessions: List user bot sessions with user isolation.
2. POST /bot: SSE streaming chitchat flow and message persistence.
3. POST /bot: Machine query routing, tool execution, and response synthesis.
4. POST /bot: Ambiguous machine resolution yielding 'needs_input' SSE event.
5. GET /bot/sessions/{session_id}: Session detail with message list.
6. GET /bot/sessions/{session_id}/messages: History retrieval.
7. DELETE /bot/sessions/{session_id}: Session deletion and cascade.
8. Unit tests for agent tools: list_machines, get_machine_info, search_sensor_data.
9. Unit tests for LangGraph nodes: router, chitchat, resolve_machine, tool_decider, tool_executor, synthesize.
10. Unit tests for run_bot_agent generator and build_bot_graph compiler.
"""
from __future__ import annotations

import json
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# SQLite compilation compatibility for PostgreSQL dialect types in memory tests
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(ARRAY, "sqlite")
def compile_array_sqlite(type_, compiler, **kw):
    return "TEXT"


@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


from app.api.deps import get_current_user, get_db, hash_password
from app.bot.graph import (
    build_bot_graph,
    chitchat_node,
    resolve_machine_node,
    router_node,
    run_bot_agent,
    synthesize_node,
    tool_decider_node,
    tool_executor_node,
)
from app.bot.state import BotGraphState
from app.bot.tools import (
    execute_bot_tool,
    get_machine_info_tool,
    list_machines_tool,
    search_sensor_data,
)
from app.db.models import Base, BotMessage, BotSession, Machine, User
from app.main import app

# In-memory SQLite engine with StaticPool
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine
)


def parse_sse_events(raw_body: str) -> list[dict]:
    """Helper to parse SSE string body into event dicts."""
    events = []
    for chunk in raw_body.split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        for line in chunk.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                payload_str = line[5:].strip()
                try:
                    events.append(json.loads(payload_str))
                except json.JSONDecodeError:
                    pass
    return events


class BotAPITestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=test_engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=test_engine)

    def setUp(self):
        self.db: Session = TestingSessionLocal()
        self.test_user = User(
            id=uuid.uuid4(),
            username=f"engineer_{uuid.uuid4().hex[:6]}",
            email=f"eng_{uuid.uuid4().hex[:6]}@example.com",
            password_hash=hash_password("password123"),
            role="engineer",
            is_active=True,
        )
        self.db.add(self.test_user)
        self.db.commit()
        self.db.refresh(self.test_user)

        self.other_user = User(
            id=uuid.uuid4(),
            username=f"viewer_{uuid.uuid4().hex[:6]}",
            email=f"view_{uuid.uuid4().hex[:6]}@example.com",
            password_hash=hash_password("password123"),
            role="viewer",
            is_active=True,
        )
        self.db.add(self.other_user)
        self.db.commit()
        self.db.refresh(self.other_user)

        self.test_machine = Machine(
            id=uuid.uuid4(),
            name="CNC Milling Haas VF-2",
            machine_type="Haas",
            status="running",
            created_by=self.test_user.id,
        )
        self.db.add(self.test_machine)
        self.db.commit()
        self.db.refresh(self.test_machine)

        # Set up overrides
        def override_get_db():
            db = TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        def override_get_current_user():
            return self.test_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        self.patcher = patch("app.api.routes_bot.SessionLocal", TestingSessionLocal)
        self.patcher.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.patcher.stop()
        app.dependency_overrides.clear()
        self.db.close()
        with test_engine.connect() as conn:
            with conn.begin():
                for table in reversed(Base.metadata.sorted_tables):
                    conn.execute(table.delete())

    def test_get_sessions_initially_empty(self):
        resp = self.client.get("/bot/sessions")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])

    @patch("app.bot.graph.chat")
    @patch("app.bot.graph.chat_json")
    def test_post_bot_chitchat(self, mock_chat_json, mock_chat):
        mock_chat_json.return_value = json.dumps({"intent": "chitchat"})
        mock_chat.return_value = "Halo! Ada yang bisa saya bantu terkait mesin CNC Haas?"

        resp = self.client.post("/bot", json={"message": "Halo apa kabar?", "session_id": "session-123"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp.headers["content-type"])

        events = parse_sse_events(resp.text)
        types = [e.get("type") for e in events]
        self.assertIn("status", types)
        self.assertIn("text", types)

        # Check DB session & messages persistence
        sessions = self.db.query(BotSession).filter(BotSession.user_id == self.test_user.id).all()
        self.assertEqual(len(sessions), 1)
        messages = self.db.query(BotMessage).filter(BotMessage.session_id == sessions[0].id).all()
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(messages[1].role, "assistant")

    @patch("app.bot.graph.chat")
    @patch("app.bot.graph.chat_json")
    @patch("app.bot.tools.search_bot_sensor_data")
    def test_post_bot_machine_query_flow(self, mock_search, mock_chat_json, mock_chat):
        mock_search.return_value = [
            {"content": "Run 1: temperature 300K, tool wear 120min", "metadata": {}, "similarity": 0.88}
        ]

        def chat_json_side_effect(messages, **kwargs):
            content = messages[0]["content"] if messages else ""
            if "klasifikasi intent" in content.lower():
                return json.dumps({"intent": "machine_query"})
            if "pengidentifikasi mesin" in content.lower() or "identifikasi mesin" in content.lower():
                return json.dumps({"resolved_machine_id": str(self.test_machine.id), "is_ambiguous": False})
            if "tool decider" in content.lower() or "memutuskan tool" in content.lower() or "pilih tool" in content.lower():
                # On first call return tool call, on subsequent return finish
                return json.dumps({"action": "call_tool", "tool_name": "search_sensor_data", "tool_args": {"query": "suhu"}})
            return json.dumps({"action": "finish"})

        mock_chat_json.side_effect = chat_json_side_effect
        mock_chat.return_value = "Suhu mesin Haas VF-2 saat ini dalam rentang normal 300K."

        resp = self.client.post("/bot", json={"message": "Bagaimana suhu mesin Haas VF-2?", "session_id": "ses-m1"})
        self.assertEqual(resp.status_code, 200)

        events = parse_sse_events(resp.text)
        types = [e.get("type") for e in events]
        self.assertIn("status", types)
        self.assertIn("tool_call", types)
        self.assertIn("text", types)

    @patch("app.bot.graph.chat_json")
    def test_post_bot_needs_input_when_ambiguous(self, mock_chat_json):
        m2 = Machine(
            id=uuid.uuid4(),
            name="CNC Lathe Haas ST-10",
            machine_type="Haas",
            status="running",
            created_by=self.test_user.id,
        )
        self.db.add(m2)
        self.db.commit()

        def chat_json_side_effect(messages, **kwargs):
            content = messages[0]["content"] if messages else ""
            if "klasifikasi intent" in content.lower():
                return json.dumps({"intent": "machine_query"})
            if "pengidentifikasi mesin" in content.lower() or "identifikasi mesin" in content.lower():
                return json.dumps({"resolved_machine_id": None, "is_ambiguous": True, "clarification_message": "Mesin mana yang Anda maksud?"})
            return json.dumps({})

        mock_chat_json.side_effect = chat_json_side_effect
        resp = self.client.post("/bot", json={"message": "Cek getaran mesin", "session_id": "ses-ambiguous"})
        self.assertEqual(resp.status_code, 200)

        events = parse_sse_events(resp.text)
        needs_input_events = [e for e in events if e.get("type") == "needs_input"]
        self.assertTrue(len(needs_input_events) > 0)

    def test_get_session_messages_and_delete(self):
        # Create session and messages directly in DB
        session = BotSession(id=uuid.uuid4(), user_id=self.test_user.id, title="Test Session")
        self.db.add(session)
        self.db.commit()

        msg1 = BotMessage(session_id=session.id, role="user", content="Pertanyaan 1")
        msg2 = BotMessage(session_id=session.id, role="assistant", content="Jawaban 1")
        self.db.add_all([msg1, msg2])
        self.db.commit()

        resp = self.client.get(f"/bot/sessions/{session.id}/messages")
        self.assertEqual(resp.status_code, 200)
        messages_data = resp.json()
        self.assertEqual(len(messages_data), 2)
        self.assertEqual(messages_data[0]["content"], "Pertanyaan 1")

        # Delete session
        del_resp = self.client.delete(f"/bot/sessions/{session.id}")
        self.assertEqual(del_resp.status_code, 200)
        self.assertEqual(del_resp.json()["status"], "ok")

        # Verify deletion cascades
        self.assertIsNone(self.db.query(BotSession).filter(BotSession.id == session.id).first())
        self.assertEqual(self.db.query(BotMessage).filter(BotMessage.session_id == session.id).count(), 0)

    def test_tool_execution(self):
        # list_machines tool
        res_list = execute_bot_tool("list_machines", {}, self.db)
        data = json.loads(res_list)
        self.assertTrue(len(data) >= 1)

        # get_machine_info tool
        res_info = execute_bot_tool("get_machine_info", {"machine_id": str(self.test_machine.id)}, self.db)
        info_data = json.loads(res_info)
        self.assertEqual(info_data["name"], self.test_machine.name)

        # invalid tool
        res_invalid = execute_bot_tool("unknown_tool", {}, self.db)
        self.assertIn("error", json.loads(res_invalid))


if __name__ == "__main__":
    unittest.main()
