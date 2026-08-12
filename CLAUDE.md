# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Predictive Maintenance Copilot for Haas CNC machines: ML failure prediction (RandomForest) + SHAP explainability + KNN case-based recommendations + Corrective RAG (LangGraph + Groq) for automated root-cause analysis, plus marketplace spare-part price lookup. See `README.md` (in Indonesian) for the full architecture, API reference, DB schema, and project status — read it before making non-trivial changes, it is kept up to date and is more detailed than this file.

`firecrawl/` is a vendored, unmodified copy of the third-party [firecrawl](https://github.com/mendableai/firecrawl) project (self-hosted because no official Docker Hub image exists). Treat it as external code — don't edit it as part of feature work in this repo, and don't apply this CLAUDE.md's conventions to it (it has its own `firecrawl/CLAUDE.md`).

## Commands

Everything runs via Docker Compose; there is no supported way to run backend/frontend outside containers (backend depends on system libs like `libgl1` for OpenCV/MinerU, and CPU-only torch wheels).

```bash
./up.sh          # docker compose -f compose.yaml -f dev.compose.yaml up --build, foreground, prints a ready banner once all services are healthy
./up.sh -d        # same, detached
docker compose -f compose.yaml -f dev.compose.yaml down
docker compose -f compose.yaml -f dev.compose.yaml logs -f backend   # or: frontend, postgres, chromadb, searxng, firecrawl-api
# Backend and frontend hot-reload from source in dev (uvicorn --reload, bun run dev)
# — no restart needed after editing backend/app/ or frontend/src/.

# Production (Dokploy/Traefik) — requires the external `dokploy-network` and
# BACKEND_DOMAIN/FRONTEND_DOMAIN set in .env:
docker compose -f compose.yaml -f prod.compose.yaml up -d --build
```

Requires a root `.env` (gitignored, real secrets — see `.env.example` and README's Environment Variables table for the full list: `DATABASE_URL`, `GROQ_API_KEY`, `CHROMA_*`, `SEARXNG_BASE_URL`, `FIRECRAWL_API_*`, `ALIBABA_COOKIES`, `JWT_SECRET`, etc.). `BACKEND_DOMAIN`/`FRONTEND_DOMAIN` are prod-only (Traefik routing), unused in dev.

Service URLs once up: frontend `http://localhost:3000`, backend `http://localhost:8002` (Swagger at `/docs`), ChromaDB `:8001`, SearXNG `:8080`, Firecrawl API `:3002`. Postgres is exposed on host port `5434` (not 5432 — see comment in `compose.yaml`).

**Alembic migrations** run automatically on backend container start (`alembic upgrade head` in the Dockerfile CMD). To create a new one, exec into the running container:

```bash
docker compose exec backend alembic revision --autogenerate -m "description"
docker compose exec backend alembic upgrade head
```

**Frontend**, if iterating outside Docker (`cd frontend`): `bun install`, `bun run dev` (Next.js dev server on `:3000`), `bun run build`, `bun run test` (Vitest).

**No test suite exists yet** in `backend/` or `frontend/` (no `pytest`/`vitest` config, no test files) — don't assume one when asked to "run the tests."

## Architecture

### Report pipeline is the core of the system

`POST /sensor/readings` (`routes_sensor.py`) synchronously runs the entire pipeline before responding — there is no async job queue:

1. Assign the reading to a "run" per machine (a run = a monotonically increasing `tool_wear_min` sequence; a decrease starts a new run).
2. Feature-engineer 4 raw sensor fields into 11 features and run the RandomForest classifier (`app/ml/predictor.py`) using the tuned `optimal_threshold`, not 0.5.
3. Explain the prediction with SHAP (`app/ml/shap_tool.py`).
4. Find similar historical cases and a "worst-case delta" safe-parameter suggestion via KNN (`app/ml/knn_tool.py`).
5. **Only if predicted_label is a failure**: run Corrective RAG (`app/rag/crag_graph.py`, LangGraph) — build a query from the SHAP interpretation, retrieve from ChromaDB (`app/rag/retriever.py`), grade relevance with the Groq LLM (`app/rag/grader.py`), fall back to SearXNG web search if irrelevant, then have the LLM produce a 3-section Indonesian answer (Apa Masalahnya / SOP Penanganan / Part Bermasalah).
6. If CRAG names a part, look up marketplace prices/links (Shopee/Tokopedia/Lazada/Alibaba) via Firecrawl + SearXNG (`app/rag/part_price_search.py`).
7. The LLM composes a final Indonesian-language markdown report from everything above.

All results are persisted. `GET /report/latest` (`routes_report.py`) never recomputes — it only reads stored results, so it's cheap and idempotent for the frontend to poll repeatedly.

### Module layout (`backend/app/`)

- `api/` — route handlers, one file per domain (`routes_auth.py`, `routes_machine.py`, `routes_sensor.py`, `routes_knowledgebase.py`, `routes_report.py`); `deps.py` has JWT auth + `require_role(min_role)` hierarchical RBAC (`viewer < engineer < admin`).
- `db/` — SQLAlchemy models (`models.py`) and Alembic migrations (`db/migrations/versions/`).
- `ml/` — RandomForest predictor, SHAP, KNN. Model artifact + tuning log live in `backend/saved/` (mounted as a volume, not baked into the image).
- `ingestion/` — PDF parsing (via vendored MinerU, see `backend/vendor/mineru_demo.py`), chunking (docs vs. sensor-run auto-chunks), duplicate detection (hash + semantic), embedding.
- `rag/` — the CRAG graph, retriever, LLM-based grader, and part-price search.
- `llm/groq_client.py` — the only Groq client; `chat()` / `chat_json()`.
- `vectorstore/chroma_client.py` — ChromaDB client; two collections, one for doc chunks, one for sensor-run chunks (`CHROMA_COLLECTION_DOCS` / `CHROMA_COLLECTION_SENSOR`).
- `schemas/` — Pydantic request/response models, one per domain, mirroring `api/`.

Almost every domain endpoint takes a `machine_id` — this is a multi-machine system (machines, sensor runs, documents, and reports are all scoped per machine).

### Known gaps (don't "fix" silently — confirm with the user first, see README's Status Pengerjaan)

- `chat_sessions`/`chat_messages`/`agent_tool_logs` tables exist via migration but the chatbot itself (`routes_chat.py`, `ChatbotPage.jsx`) is not implemented.
- Most read-only GET endpoints (document/chunk lists, runs, history, report) do not enforce auth even though the frontend always sends a token — only mutating/admin endpoints use `require_role`/`get_current_user`.
- `machines.status` is a static `"running"` value for every machine; no real-time PLC/OPC-UA feed exists.
- `POST /sensor/readings/batch` exists but nothing calls it yet (intended for a future Airflow/DAG integration).
- Unused `SUPABASE_*` env vars remain in `.env` from earlier work.

### Frontend (`frontend/src/`)

Next.js 16 App Router (TypeScript, Tailwind v4, shadcn/ui, Bun), ported from the sibling `wo_m_ai` project — see `docs/superpowers/specs/2026-08-11-womai-frontend-foundation-design.md` for the full migration rationale. BFF pattern: every backend call happens server-side (Server Actions / Route Handlers under `src/app/actions/`), the browser never calls the FastAPI backend directly. Auth uses an httpOnly cookie holding the JWT from `POST /auth/login` (`src/lib/auth/session.ts`); `src/middleware.ts` only checks the cookie's presence, not its validity. Pages: `/login`, `/register`, `/chat` + `/chat/[id]` (chat UI, currently backed by mock scenarios in `src/lib/mock/` — no real `/chat` backend endpoint exists yet), `/mesin` and `/sop` (CRUD UI over in-memory dummy data, not yet persisted, and shared across all users of the server process (not per-user)), `/riwayat` (chat history list). PWA-installable (`src/app/manifest.ts`, `public/sw.js`). Session cookie uses `secure: true` in production (correct Next.js practice) — this means login only works when accessed via `http://localhost:3000` from the same machine; accessing the app via a LAN IP or hostname over plain HTTP will silently drop the cookie until TLS is added in front of the app.
