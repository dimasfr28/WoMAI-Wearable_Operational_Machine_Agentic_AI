# Bot API — Agentic AI Chatbot Design

**Date:** 2026-08-15  
**Status:** Approved  
**Scope:** Backend only (frontend nanti)

## Overview

API baru `POST /bot` di dalam grup `chat` — free-form agentic AI chatbot berbasis LangGraph + Groq. Berbeda dengan `/chat` yang punya format intent terstruktur (predict/latest_report/sop_lookup/chitchat), `/bot` adalah chatbot bebas yang memakai agent loop: LLM memutuskan sendiri tools mana yang perlu dipanggil untuk menjawab pertanyaan user.

Data yang diakses berasal dari sensor readings di PostgreSQL (bukan semantic search ke ChromaDB). Model dan RAG pipeline terpisah dari `/chat`.

### Key Decisions

- **Framework:** LangGraph (konsisten dengan CRAG yang sudah ada)
- **LLM:** Groq (reuse `llm/groq_client.py`)
- **Stateful:** Session-based, conversation history disimpan di DB
- **DB:** Tabel baru (`bot_sessions`, `bot_messages`), terpisah dari `chat_sessions`/`chat_messages`
- **Response:** SSE streaming word-by-word (pola sama dengan `/chat`)
- **Auth:** JWT, `require_role("viewer")` — semua user login bisa pakai
- **Machine scope:** Default per-mesin, tapi fleksibel lintas mesin kalau ditanya

## Graph Architecture

```
User message + history
        │
        ▼
  ┌─────────────┐
  │  LLM Router  │  ← Decide: butuh data mesin? chitchat?
  └──────┬───────┘
         │
    ┌────┴─────┐
    │          │
    ▼          ▼
┌────────┐  ┌──────────────┐
│Chitchat│  │Resolve Machine│ ← Identifikasi mesin mana dari pesan user
│ (end)  │  └──────┬───────┘    (LLM match nama mesin ke daftar DB,
└────────┘         │             atau tanya balik kalau ambigu)
                   │
                   ▼
           ┌──────────────┐
           │ Sensor Tools │ ← ReAct sub-loop: LLM pilih tool mana
           │   (loop)     │    yang perlu dipanggil
           └──────┬───────┘
                  │
                  ▼
           ┌──────────────┐
           │  Synthesize  │ ← LLM rangkum hasil tools jadi jawaban
           │  & Stream    │    bahasa Indonesia, stream word-by-word
           └──────────────┘
```

### Node Details

**1. LLM Router**
- Input: pesan user + conversation history (sliding window 20 pesan terakhir)
- Output: `"machine_query"` atau `"chitchat"`
- Satu LLM call dengan system prompt yang mengarahkan klasifikasi
- Chitchat: sapaan, pertanyaan umum CNC yang tidak butuh data spesifik

**2. Resolve Machine**
- Input: pesan user + conversation history + daftar mesin dari DB
- Output: `machine_id` yang resolved, atau `needs_input` event
- LLM mencocokkan nama mesin yang disebut user ke daftar mesin di DB
- Kalau session sudah punya `machine_id` sebelumnya (dari pesan lalu) dan user tidak sebut mesin baru, pakai itu sebagai default
- Kalau ambigu atau tidak disebut: stream `needs_input` ke user
- Update `bot_sessions.machine_id` setiap kali mesin baru di-resolve

**3. Sensor Tools (ReAct Loop)**
- Input: pertanyaan user + `machine_id` yang sudah resolved
- LLM memutuskan tool mana yang perlu dipanggil, bisa >1 tool
- Hard limit: max 5 tool calls per request
- Tools tersedia:

| Tool | Deskripsi | Data Source |
|---|---|---|
| `get_sensor_history(machine_id)` | Time-series data sensor run terbaru + IQR anomaly flags + statistik | `sensor_readings` table |
| `get_latest_prediction(machine_id)` | Prediksi ML terakhir (label, probabilitas, health score) | `predictions` table |
| `get_machine_status(machine_id)` | Status operasional mesin + early warning | `machines` table + derived |
| `list_machines()` | Daftar semua mesin terdaftar | `machines` table |
| `get_sensor_runs(machine_id)` | Daftar run/sesi kerja suatu mesin | `sensor_runs` table |
| `get_prediction_history(machine_id, limit)` | Riwayat prediksi sebelumnya | `predictions` table |

**4. Synthesize & Stream**
- Input: data dari tools + pertanyaan user
- LLM menyusun jawaban final dalam Bahasa Indonesia
- Stream SSE word-by-word ke client

## Database Schema

Tabel baru, terpisah dari `chat_sessions`/`chat_messages`:

```sql
-- Session percakapan bot
CREATE TABLE bot_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    title           VARCHAR(255) NOT NULL DEFAULT 'Chat baru',
    machine_id      UUID REFERENCES machines(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_bot_sessions_user_id ON bot_sessions(user_id);

-- Pesan dalam session bot
CREATE TYPE bot_message_role AS ENUM ('user', 'assistant', 'tool');

CREATE TABLE bot_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES bot_sessions(id) ON DELETE CASCADE,
    role            bot_message_role NOT NULL,
    content         TEXT NOT NULL,
    tool_name       VARCHAR(100),
    tool_call_id    VARCHAR(100),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_bot_messages_session_id ON bot_messages(session_id);
```

`bot_sessions.machine_id`: mesin terakhir yang di-resolve — sebagai default konteks untuk pesan berikutnya tanpa perlu tanya ulang.

Migrasi via Alembic autogenerate.

## API Endpoints

### Chat

| Method | Path | Auth | Body | Response | Deskripsi |
|---|---|---|---|---|---|
| `POST` | `/bot` | user login | `{ "message": str, "session_id": str }` | SSE stream | Kirim pesan, terima jawaban streaming |

### Session Management

| Method | Path | Auth | Deskripsi |
|---|---|---|---|
| `GET` | `/bot/sessions` | user login | List semua session milik user (untuk sidebar/daftar room) |
| `GET` | `/bot/sessions/{session_id}/messages` | user login | Ambil riwayat pesan session tertentu |
| `DELETE` | `/bot/sessions/{session_id}` | user login | Hapus session + semua pesannya |

### SSE Event Types

| Event type | Kapan | Payload |
|---|---|---|
| `status` | Agent sedang bekerja | `{ "message": "Mencari data sensor mesin X..." }` |
| `tool_call` | Agent memanggil tool (opsional, transparansi) | `{ "name": "get_sensor_history", "machine_id": "..." }` |
| `needs_input` | Mesin ambigu / tidak disebut | `{ "message": "Mesin mana yang dimaksud?" }` |
| `text` | Jawaban final, word-by-word | `{ "delta": "Berdasarkan " }` |
| `error` | Error | `{ "message": "..." }` |

### Request Schema

```python
class BotIn(BaseModel):
    message: str
    session_id: str
```

## Module Layout

```
backend/app/
├── api/
│   └── routes_bot.py          # POST /bot + GET/DELETE session endpoints, SSE streaming
├── schemas/
│   └── bot.py                 # BotIn, BotSessionOut, BotMessageOut
├── bot/                       # NEW — modul agent khusus /bot
│   ├── __init__.py
│   ├── graph.py               # LangGraph StateGraph (router → resolve_machine → sensor_tools → synthesize)
│   ├── state.py               # TypedDict untuk graph state
│   ├── tools.py               # Tool functions (get_sensor_history, dll.)
│   └── prompts.py             # System prompts per node
├── db/
│   ├── models.py              # + BotSession, BotMessage models
│   └── migrations/versions/
│       └── xxxx_add_bot_tables.py
```

Reuse existing modules:
- `llm/groq_client.py` — LLM calls
- `db/models.py` — query sensor tables (SensorReading, Prediction, SensorRun, Machine)
- `api/deps.py` — JWT auth, `get_current_user`

## Conversation History

- Setiap request, ambil **20 pesan terakhir** dari `bot_messages` untuk session tersebut (sliding window)
- Dikirim sebagai `messages[]` ke LLM di setiap node yang butuh context
- Tool call results (`role='tool'`) juga masuk history
- Session UUID di-derive deterministik: `uuid5(user.id + session_id)`

**DB session handling:** Buat `SessionLocal()` baru di dalam SSE generator (bukan `Depends(get_db)`), karena FastAPI menutup dependency session sebelum generator selesai streaming. Pola sama dengan `routes_chat.py`.

## Error Handling

| Scenario | Handling |
|---|---|
| Groq API down / rate limit | Stream `error` event. Pesan user tetap tersimpan. |
| Machine tidak ditemukan / ambigu | Stream `needs_input` dengan daftar mesin. |
| Data sensor kosong | Agent jawab natural: "Belum ada data sensor untuk mesin X." |
| Session tidak ditemukan (GET/DELETE) | HTTP 404 |
| User tidak login | HTTP 401 |
| Tool loop >5 calls | Hard limit, paksa ke Synthesize. |
| Pesan kosong | HTTP 422 (Pydantic validation) |
| Timeout >60 detik | Stream error gracefully. |

## Out of Scope

- Frontend (halaman chat `/bot` di Next.js) — akan didesain terpisah
- RAG/semantic search ke ChromaDB — `/bot` query structured data dari PostgreSQL saja
- Integrasi dengan CRAG pipeline (`rag/`) — `/bot` punya graph sendiri
- Websocket — SSE cukup untuk saat ini
