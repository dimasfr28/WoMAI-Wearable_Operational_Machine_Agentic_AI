# Dev/Prod Docker Compose Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single `docker-compose.yml` with a base + override structure (`compose.yaml` + `dev.compose.yaml` + `prod.compose.yaml`) so `backend`/`frontend` can hot-reload in dev and route through Traefik/Dokploy in prod, while the shared vendored services (Postgres, ChromaDB, SearXNG, Firecrawl cluster) stay defined once.

**Architecture:** `compose.yaml` holds everything environment-agnostic (no `backend`/`frontend` service — those move entirely into the two overlay files). `dev.compose.yaml` adds `backend`/`frontend` built from new `Dockerfile.dev` files with bind-mounted source for hot reload. `prod.compose.yaml` adds the same two services built from new `Dockerfile.prod` files, with Traefik labels and no published host ports (routing happens via the external `dokploy-network`).

**Tech Stack:** Docker Compose (multi-file `-f` merge), no new runtime dependencies.

## Global Constraints

- Every new/modified compose file must be valid YAML that `docker compose config` accepts without error (Postgres/env-derived variable warnings aside — those require a real `.env`, not something this plan's tasks can supply).
- `compose.yaml`'s shared services (`postgres`, `chromadb`, `searxng`, `firecrawl-*`) must be byte-for-byte unchanged in content — only their file location changes.
- `backend/Dockerfile.prod` and `frontend/Dockerfile.prod`'s build logic must be unchanged from what's in the current `backend/Dockerfile` / `frontend/Dockerfile` today — only file location/naming changes, no behavior change.
- `backend/Dockerfile.dev` and `frontend/Dockerfile.dev` differ from their `.prod` counterparts only in the ways specified per-task below (hot reload CMD / stage selection) — no other divergence.
- No host ports published for `backend`/`frontend` in `prod.compose.yaml` — Traefik routing only.
- `${BACKEND_DOMAIN}` / `${FRONTEND_DOMAIN}` are placeholders — no real domain names anywhere in this plan.
- This plan does not attempt to solve the empty-`backend_saved`-volume-on-first-prod-deploy gap (documented in the design spec) — it's an operational note, out of scope for the compose files themselves.

---

### Task 1: Create `compose.yaml` (base) with the shared services

**Files:**
- Create: `compose.yaml`
- Read (not modified in this task): `docker-compose.yml` (source to extract from)

**Interfaces:**
- Produces: a `compose.yaml` containing exactly the `postgres`, `chromadb`, `searxng`, `firecrawl-playwright`, `firecrawl-redis`, `firecrawl-rabbitmq`, `firecrawl-nuq-postgres`, `firecrawl-api` services plus the top-level `networks:` (`default`, `firecrawl_backend`) and `volumes:` (`pgdata`, `chromadata`) blocks — everything from `docker-compose.yml` EXCEPT `backend` and `frontend`. Later tasks (`dev.compose.yaml`, `prod.compose.yaml`) depend on this file existing with exactly this service set, since `docker compose -f compose.yaml -f dev.compose.yaml` needs `backend`'s `depends_on: postgres, firecrawl-api` to resolve against services defined here.

- [ ] **Step 1: Create `compose.yaml`**

Copy the following into a new file `compose.yaml` at the repo root — this is `docker-compose.yml`'s current content with the `backend:` and `frontend:` service blocks removed (everything else, including every comment, is verbatim):

```yaml
services:
  postgres:
    image: postgres:16
    env_file: .env
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      # Host port changed from 5432 -> 5433 -> 5434: 5432 is taken by a native
      # (non-Docker) PostgreSQL systemd service on this machine, and 5433 was
      # later taken by an unrelated container ("led-postgres") from another
      # project. Container-internal port stays 5432 (DATABASE_URL in .env is
      # unaffected — it connects via the "postgres" service name/port).
      - "5434:5432"
    healthcheck:
      # -d added: without it, pg_isready defaults to a database named after
      # POSTGRES_USER ("comfest"), which doesn't exist (the real db is
      # "comfest_db") — harmless for the healthcheck result itself, but spams
      # the log with "FATAL: database "comfest" does not exist" every few
      # seconds.
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10

  chromadb:
    image: chromadb/chroma:0.5.20
    volumes:
      - chromadata:/chroma/chroma
    ports:
      - "8001:8000"

  searxng:
    image: searxng/searxng:latest
    volumes:
      - ./searxng:/etc/searxng
    ports:
      - "8080:8080"

  # --- Firecrawl (self-hosted from source, see app/firecrawl/) ---
  # Official image `mendableai/firecrawl` does not exist on Docker Hub, so it is
  # built from the cloned source (github.com/mendableai/firecrawl) instead.
  # Adapted from app/firecrawl/docker-compose.yaml. `foundationdb`/`foundationdb-init`
  # (experimental alt queue backend) intentionally omitted — nuq-postgres is the default.

  firecrawl-playwright:
    build: ./firecrawl/apps/playwright-service-ts
    environment:
      PORT: 3000
      PROXY_SERVER:
      PROXY_USERNAME:
      PROXY_PASSWORD:
      ALLOW_LOCAL_WEBHOOKS:
      BLOCK_MEDIA:
      MAX_CONCURRENT_PAGES: 10
    networks:
      - firecrawl_backend
    # Lowered from upstream default (cpus: 2.0, mem_limit: 4G) for dev laptops.
    # Raise back toward the upstream default for production.
    cpus: 1.0
    mem_limit: 1G
    memswap_limit: 1G
    tmpfs:
      - /tmp/.cache:noexec,nosuid,size=512m

  firecrawl-redis:
    image: redis:alpine
    networks:
      - firecrawl_backend
    command: redis-server --bind 0.0.0.0

  firecrawl-rabbitmq:
    image: rabbitmq:3-management
    networks:
      - firecrawl_backend
    command: rabbitmq-server
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "check_running"]
      interval: 5s
      timeout: 5s
      retries: 3
      start_period: 5s

  # Firecrawl's OWN Postgres (job queue storage), fully separate from the main
  # `postgres` service above — different schema/purpose. Not exposed on the host
  # (no ports:), so it can never collide with the comfest postgres on 5432.
  firecrawl-nuq-postgres:
    build: ./firecrawl/apps/nuq-postgres
    environment:
      POSTGRES_USER: firecrawl
      POSTGRES_PASSWORD: firecrawl
      POSTGRES_DB: firecrawl
    networks:
      - firecrawl_backend

  # Renamed from upstream `api` to `firecrawl-api` to avoid ambiguity with other
  # services and make its role explicit in the combined compose file.
  firecrawl-api:
    build: ./firecrawl/apps/api
    environment:
      REDIS_URL: redis://firecrawl-redis:6379
      REDIS_RATE_LIMIT_URL: redis://firecrawl-redis:6379
      PLAYWRIGHT_MICROSERVICE_URL: http://firecrawl-playwright:3000/scrape
      POSTGRES_USER: firecrawl
      POSTGRES_PASSWORD: firecrawl
      POSTGRES_DB: firecrawl
      POSTGRES_HOST: firecrawl-nuq-postgres
      POSTGRES_PORT: 5432
      USE_DB_AUTHENTICATION: "false"
      NUM_WORKERS_PER_QUEUE: 8
      CRAWL_CONCURRENT_REQUESTS: 10
      MAX_CONCURRENT_JOBS: 5
      BROWSER_POOL_SIZE: 5
      # AI-based structured extraction (Firecrawl's own LLM features) intentionally
      # left empty — we only use plain-text scraping via /v1/scrape; Groq parses
      # the scraped text ourselves in backend/app/rag/part_price_search.py.
      OPENAI_API_KEY:
      OPENAI_BASE_URL:
      MODEL_NAME:
      MODEL_EMBEDDING_NAME:
      OLLAMA_BASE_URL:
      AUTUMN_SECRET_KEY:
      SLACK_WEBHOOK_URL:
      BULL_AUTH_KEY:
      TEST_API_KEY:
      SUPABASE_ANON_TOKEN:
      SUPABASE_URL:
      SUPABASE_SERVICE_TOKEN:
      SELF_HOSTED_WEBHOOK_URL:
      LOGGING_LEVEL:
      PROXY_SERVER:
      PROXY_USERNAME:
      PROXY_PASSWORD:
      SEARXNG_ENDPOINT: http://searxng:8080
      SEARXNG_ENGINES:
      SEARXNG_CATEGORIES:
      NUQ_BACKEND:
      HOST: "0.0.0.0"
      PORT: 3002
      EXTRACT_WORKER_PORT: 3004
      WORKER_PORT: 3005
      NUQ_RABBITMQ_URL: amqp://firecrawl-rabbitmq:5672
      HARNESS_STARTUP_TIMEOUT_MS: 60000
      ENV: local
    ulimits:
      nofile:
        soft: 65535
        hard: 65535
    depends_on:
      firecrawl-redis:
        condition: service_started
      firecrawl-playwright:
        condition: service_started
      firecrawl-rabbitmq:
        condition: service_healthy
      firecrawl-nuq-postgres:
        condition: service_started
      searxng:
        condition: service_started
    command: node dist/src/harness.js --start-docker
    ports:
      - "3002:3002"
    # Present on both networks: `firecrawl_backend` to talk to its own
    # redis/rabbitmq/postgres/playwright, and the default network so the
    # comfest `backend` service can reach it as `firecrawl-api`.
    networks:
      - firecrawl_backend
      - default
    # Lowered from upstream default (cpus: 4.0, mem_limit: 8G) for dev laptops,
    # but raised from an earlier 2G attempt: this single container runs the
    # harness's 9 child Node.js processes at once (api, worker, extract-worker,
    # 5x nuq-worker, nuq-prefetch-worker, nuq-reconciler) — 2G was too tight and
    # caused the kernel OOM-killer to SIGKILL nuq-worker-N (exit 137) a few
    # seconds after startup. Raise further toward the upstream 8G default for
    # production / heavier crawl loads.
    cpus: 1.5
    mem_limit: 4G
    memswap_limit: 4G

networks:
  default:
  firecrawl_backend:

volumes:
  pgdata:
  chromadata:
```

- [ ] **Step 2: Validate the file is syntactically valid YAML**

Run: `docker compose -f compose.yaml config --quiet 2>&1 | head -20`
Expected: no YAML parse errors. It's fine (expected, not a failure) if this reports something like `service "postgres" refers to undefined volume ...` or complains about missing env var interpolation for `${POSTGRES_USER}`/`${POSTGRES_DB}` if no `.env` exists in this environment — that's a pre-existing, unrelated condition (no `.env` file exists in this repo at all yet), not something this task introduces or must fix. If you need to confirm the YAML itself parses, you can additionally run `docker compose -f compose.yaml config >/dev/null` with a throwaway local `.env` containing at least `POSTGRES_USER=x` and `POSTGRES_DB=y` (do NOT commit that throwaway `.env`).

- [ ] **Step 3: Commit**

```bash
git add compose.yaml
git commit -m "chore: extract shared services into compose.yaml base"
```

(Do not delete `docker-compose.yml` in this task — that happens in Task 5, once its full replacement exists.)

---

### Task 2: Split frontend and backend Dockerfiles into `.dev`/`.prod` variants

**Files:**
- Create: `frontend/Dockerfile.dev`
- Create: `frontend/Dockerfile.prod`
- Create: `backend/Dockerfile.dev`
- Create: `backend/Dockerfile.prod`
- Read (not modified): `frontend/Dockerfile`, `backend/Dockerfile` (sources to split from)

**Interfaces:**
- Produces: 4 new Dockerfiles that `dev.compose.yaml` (Task 3) and `prod.compose.yaml` (Task 4) will reference via `build.dockerfile:`. Their exact filenames (`Dockerfile.dev`/`Dockerfile.prod` in each of `frontend/` and `backend/`) are load-bearing — later tasks reference these names verbatim.

- [ ] **Step 1: Create `frontend/Dockerfile.dev`**

```dockerfile
# syntax=docker/dockerfile:1

# ============================================================
# Frontend (Next.js) - development image (Bun, hot-reload)
# ============================================================

FROM oven/bun:1-alpine
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

COPY . .
EXPOSE 3000
CMD ["bun", "run", "dev"]
```

- [ ] **Step 2: Create `frontend/Dockerfile.prod`**

```dockerfile
# syntax=docker/dockerfile:1

# ============================================================
# Frontend (Next.js) - production image (Bun build, Node runtime)
# ============================================================

FROM oven/bun:1-alpine AS deps
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

# ---------- build ----------
FROM deps AS builder
COPY . .
RUN bun run build

# ---------- production ----------
# Runner tetap Node: entrypoint standalone Next.js dijalankan `node server.js`
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
```

- [ ] **Step 3: Delete the old `frontend/Dockerfile`**

```bash
git rm frontend/Dockerfile
```

- [ ] **Step 4: Create `backend/Dockerfile.prod`**

Copy the current `backend/Dockerfile` content exactly as-is into a new file `backend/Dockerfile.prod` — every line, every comment, unchanged:

```dockerfile
FROM python:3.11-slim

# Host has no working IPv6 route AND TCP port 53 (DNS-over-TCP) is blocked on this
# network. download.pytorch.org's AAAA answer alone exceeds the 512-byte classic UDP
# DNS limit, so glibc's getaddrinfo() gets a truncated (TC=1) UDP response and retries
# over TCP — which then hangs forever since TCP:53 never connects. Reprioritizing IPv4
# (gai.conf) isn't enough because the AAAA query itself still stalls; RES_OPTIONS=no-aaaa
# (glibc 2.34+) skips AAAA queries entirely, avoiding the truncation/TCP-fallback path.
ENV RES_OPTIONS="no-aaaa"

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.cache/huggingface \
    # MinerU (pipeline backend) is vendored fully into this image so PDF parsing
    # never depends on an external MinerU service. Model downloads MUST go via
    # ModelScope, not HuggingFace — HF is unusably slow/stalls on this network,
    # ModelScope is fast and reliable. This has to be set before any `mineru`
    # invocation (build-time pre-download below AND at container runtime) so both
    # paths use the same mirror.
    MINERU_MODEL_SOURCE=modelscope

# libgl1/libglib2.0-0: required at runtime by opencv-python (cv2), a transitive
# dependency of mineru[pipeline]'s layout/OCR stack — the slim base image lacks
# the shared libs cv2 dlopens, so import fails without them even though the
# wheel itself installs fine.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# All pinned dependencies ship manylinux wheels (scikit-learn, shap, chromadb,
# sentence-transformers/torch, psycopg[binary], mineru[pipeline]'s own deps), so
# build-essential/gcc is not needed and is skipped to keep the image lean and
# the build fast.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# hf-xet (huggingface_hub's newer "xet-bridge" transfer protocol, now a hard
# dependency pulled in transitively by sentence-transformers) hangs/stalls
# indefinitely downloading model.safetensors on this network — HF_HUB_DISABLE_XET=1
# does NOT actually disable it in this version, only *uninstalling* the package
# does (huggingface_hub then logs a warning and correctly falls back to plain
# HTTP download, which works fine — same class of CDN issue as
# download.pytorch.org/ModelScope elsewhere in this Dockerfile, different vendor).
RUN pip uninstall -y hf-xet

# Vendor MinerU's demo/api_client-driven parsing helper (demo/demo.py upstream at
# github.com/opendatalab/MinerU) — this is the pattern verified in
# code/knowledgebase.ipynb to actually work: it spawns a local `mineru-api`
# FastAPI subprocess (mineru.cli.fast_api) and drives it over HTTP via
# mineru.cli.api_client, rather than any direct "parse this PDF" python function
# (no such simple function exists in the mineru package). demo.py itself is a
# small standalone script, not part of the installed `mineru` PyPI package, so it
# is copied in explicitly rather than pulled in via pip.
COPY vendor/mineru_demo.py /app/vendor/mineru_demo.py

# Pre-download MinerU pipeline models at build time (Opsi A) so the container
# starts ready to parse immediately instead of blocking the first upload
# request on a multi-hundred-MB model download. Uses the mineru-models-download
# CLI (installed by mineru[pipeline] above) with --source modelscope explicitly
# (belt-and-suspenders alongside the MINERU_MODEL_SOURCE env above).
RUN mineru-models-download --source modelscope --model_type pipeline

COPY . .

EXPOSE 8000

CMD ["bash", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

- [ ] **Step 5: Create `backend/Dockerfile.dev`**

Same content as `backend/Dockerfile.prod` from Step 4, with only the final `CMD` line changed:

```dockerfile
FROM python:3.11-slim

# Host has no working IPv6 route AND TCP port 53 (DNS-over-TCP) is blocked on this
# network. download.pytorch.org's AAAA answer alone exceeds the 512-byte classic UDP
# DNS limit, so glibc's getaddrinfo() gets a truncated (TC=1) UDP response and retries
# over TCP — which then hangs forever since TCP:53 never connects. Reprioritizing IPv4
# (gai.conf) isn't enough because the AAAA query itself still stalls; RES_OPTIONS=no-aaaa
# (glibc 2.34+) skips AAAA queries entirely, avoiding the truncation/TCP-fallback path.
ENV RES_OPTIONS="no-aaaa"

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.cache/huggingface \
    # MinerU (pipeline backend) is vendored fully into this image so PDF parsing
    # never depends on an external MinerU service. Model downloads MUST go via
    # ModelScope, not HuggingFace — HF is unusably slow/stalls on this network,
    # ModelScope is fast and reliable. This has to be set before any `mineru`
    # invocation (build-time pre-download below AND at container runtime) so both
    # paths use the same mirror.
    MINERU_MODEL_SOURCE=modelscope

# libgl1/libglib2.0-0: required at runtime by opencv-python (cv2), a transitive
# dependency of mineru[pipeline]'s layout/OCR stack — the slim base image lacks
# the shared libs cv2 dlopens, so import fails without them even though the
# wheel itself installs fine.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# All pinned dependencies ship manylinux wheels (scikit-learn, shap, chromadb,
# sentence-transformers/torch, psycopg[binary], mineru[pipeline]'s own deps), so
# build-essential/gcc is not needed and is skipped to keep the image lean and
# the build fast.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# hf-xet (huggingface_hub's newer "xet-bridge" transfer protocol, now a hard
# dependency pulled in transitively by sentence-transformers) hangs/stalls
# indefinitely downloading model.safetensors on this network — HF_HUB_DISABLE_XET=1
# does NOT actually disable it in this version, only *uninstalling* the package
# does (huggingface_hub then logs a warning and correctly falls back to plain
# HTTP download, which works fine — same class of CDN issue as
# download.pytorch.org/ModelScope elsewhere in this Dockerfile, different vendor).
RUN pip uninstall -y hf-xet

# Vendor MinerU's demo/api_client-driven parsing helper (demo/demo.py upstream at
# github.com/opendatalab/MinerU) — this is the pattern verified in
# code/knowledgebase.ipynb to actually work: it spawns a local `mineru-api`
# FastAPI subprocess (mineru.cli.fast_api) and drives it over HTTP via
# mineru.cli.api_client, rather than any direct "parse this PDF" python function
# (no such simple function exists in the mineru package). demo.py itself is a
# small standalone script, not part of the installed `mineru` PyPI package, so it
# is copied in explicitly rather than pulled in via pip.
COPY vendor/mineru_demo.py /app/vendor/mineru_demo.py

# Pre-download MinerU pipeline models at build time (Opsi A) so the container
# starts ready to parse immediately instead of blocking the first upload
# request on a multi-hundred-MB model download. Uses the mineru-models-download
# CLI (installed by mineru[pipeline] above) with --source modelscope explicitly
# (belt-and-suspenders alongside the MINERU_MODEL_SOURCE env above).
RUN mineru-models-download --source modelscope --model_type pipeline

COPY . .

EXPOSE 8000

CMD ["bash", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
```

- [ ] **Step 6: Delete the old `backend/Dockerfile`**

```bash
git rm backend/Dockerfile
```

- [ ] **Step 7: Verify the diff between the two backend Dockerfiles is exactly the CMD line**

Run: `diff backend/Dockerfile.prod backend/Dockerfile.dev`
Expected output (exactly this, nothing more):
```
69c69
< CMD ["bash", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
---
> CMD ["bash", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
```

- [ ] **Step 8: Commit**

```bash
git add frontend/Dockerfile.dev frontend/Dockerfile.prod backend/Dockerfile.dev backend/Dockerfile.prod
git commit -m "chore: split frontend and backend Dockerfiles into dev/prod variants"
```

---

### Task 3: Create `dev.compose.yaml`

**Files:**
- Create: `dev.compose.yaml`

**Interfaces:**
- Consumes: `frontend/Dockerfile.dev`, `backend/Dockerfile.dev` (Task 2); `postgres`, `firecrawl-api` service names from `compose.yaml` (Task 1) for the `depends_on` block to resolve when merged via `-f compose.yaml -f dev.compose.yaml`.
- Produces: `backend` and `frontend` services usable as the default local dev overlay.

- [ ] **Step 1: Create `dev.compose.yaml`**

```yaml
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.dev
    env_file: .env
    volumes:
      - ./backend:/app
      - ./backend/saved:/app/saved
      # PDF library lives on the host at /home/dimas/comfest/document (outside
      # the repo/build context) so uploads and pre-existing manuals share one
      # place; the "data" subfolder (dataset.csv, already handled by migration
      # 0003) is intentionally NOT mounted here — PDF_LIBRARY_DIR points at the
      # library root, and dataset.csv seeding stays a separate concern.
      - /home/dimas/comfest/document:/data/pdf_library
    depends_on:
      postgres:
        condition: service_healthy
      firecrawl-api:
        condition: service_started
    ports:
      # Host port changed from 8000 -> 8002: an unrelated container ("led-api",
      # different project) already holds 8000 on this machine. Container-internal
      # port stays 8000.
      - "8002:8000"

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.dev
    environment:
      BACKEND_URL: "http://backend:8000"
    volumes:
      # Hot-reload: source di-mount, node_modules & .next tetap milik container
      - ./frontend:/app
      - /app/node_modules
      - /app/.next
    depends_on:
      - backend
    ports:
      - "3000:3000"
```

- [ ] **Step 2: Validate the merged config parses**

Run: `docker compose -f compose.yaml -f dev.compose.yaml config --quiet 2>&1 | head -20`
Expected: no YAML/merge errors (`services.backend.build.dockerfile` should resolve to `Dockerfile.dev`, `depends_on.postgres`/`depends_on.firecrawl-api` should resolve against `compose.yaml`'s services without a "service not found" error). As in Task 1, missing-env-var warnings for `${POSTGRES_USER}` etc. are expected and unrelated to this task if no `.env` exists yet.

- [ ] **Step 3: Commit**

```bash
git add dev.compose.yaml
git commit -m "chore: add dev.compose.yaml overlay (hot-reload backend + frontend)"
```

---

### Task 4: Create `prod.compose.yaml`

**Files:**
- Create: `prod.compose.yaml`

**Interfaces:**
- Consumes: `frontend/Dockerfile.prod`, `backend/Dockerfile.prod` (Task 2); `postgres`, `firecrawl-api` service names from `compose.yaml` (Task 1).
- Produces: `backend` and `frontend` services for the Dokploy/Traefik-routed production overlay.

- [ ] **Step 1: Create `prod.compose.yaml`**

```yaml
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.prod
    env_file: .env
    volumes:
      - backend_saved:/app/saved
      - pdf_library:/data/pdf_library
    depends_on:
      postgres:
        condition: service_healthy
      firecrawl-api:
        condition: service_started
    networks:
      - default
      - dokploy-network
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.comfest-backend.rule=Host(`${BACKEND_DOMAIN}`)"
      - "traefik.http.routers.comfest-backend.entrypoints=websecure"
      - "traefik.http.routers.comfest-backend.tls.certResolver=letsencrypt"
      - "traefik.http.services.comfest-backend.loadbalancer.server.port=8000"

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.prod
    environment:
      BACKEND_URL: "http://backend:8000"
    depends_on:
      - backend
    networks:
      - default
      - dokploy-network
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.comfest-frontend.rule=Host(`${FRONTEND_DOMAIN}`)"
      - "traefik.http.routers.comfest-frontend.entrypoints=websecure"
      - "traefik.http.routers.comfest-frontend.tls.certResolver=letsencrypt"
      - "traefik.http.services.comfest-frontend.loadbalancer.server.port=3000"

networks:
  dokploy-network:
    external: true

volumes:
  backend_saved:
  pdf_library:
```

- [ ] **Step 2: Validate the merged config parses**

Run: `docker compose -f compose.yaml -f prod.compose.yaml config --quiet 2>&1 | head -30`

This will report an error about the external network `dokploy-network` not existing — that's expected in any environment that isn't an actual Dokploy host (this plan doesn't create that network). To confirm the YAML itself is otherwise well-formed, additionally run:

Run: `docker compose -f compose.yaml -f prod.compose.yaml config --quiet --no-interpolate 2>&1 | grep -i "yaml\|parse" `
Expected: no output (no YAML parse errors). Report the `dokploy-network`-not-found error in your task report as expected/known, not a defect.

- [ ] **Step 3: Commit**

```bash
git add prod.compose.yaml
git commit -m "chore: add prod.compose.yaml overlay (Traefik/Dokploy routing)"
```

---

### Task 5: Remove `docker-compose.yml`, update `up.sh`

**Files:**
- Delete: `docker-compose.yml`
- Modify: `up.sh`

**Interfaces:**
- Consumes: `compose.yaml` + `dev.compose.yaml` (Tasks 1 and 3) as the file set `up.sh` now drives.

- [ ] **Step 1: Delete `docker-compose.yml`**

```bash
git rm docker-compose.yml
```

- [ ] **Step 2: Update `up.sh`**

In `up.sh`, find this block:
```bash
if [[ "${1:-}" == "-d" ]]; then
  docker compose up --build
  wait_for_ready
  exit 0
fi

# Foreground mode: run the ready-check in the background against the compose
# project while streaming (and filtering) the live log in the foreground.
wait_for_ready &
READY_PID=$!
trap 'kill "$READY_PID" 2>/dev/null || true' EXIT

docker compose up --build 2>&1 | grep -vE "$NOISE_PATTERN"
```
Replace it with:
```bash
if [[ "${1:-}" == "-d" ]]; then
  docker compose -f compose.yaml -f dev.compose.yaml up --build
  wait_for_ready
  exit 0
fi

# Foreground mode: run the ready-check in the background against the compose
# project while streaming (and filtering) the live log in the foreground.
wait_for_ready &
READY_PID=$!
trap 'kill "$READY_PID" 2>/dev/null || true' EXIT

docker compose -f compose.yaml -f dev.compose.yaml up --build 2>&1 | grep -vE "$NOISE_PATTERN"
```

Also find this line inside the `wait_for_ready` function:
```bash
    rows="$(docker compose ps --format '{{.Service}} {{.State}} {{.Health}}' 2>/dev/null || true)"
```
Replace it with:
```bash
    rows="$(docker compose -f compose.yaml -f dev.compose.yaml ps --format '{{.Service}} {{.State}} {{.Health}}' 2>/dev/null || true)"
```

- [ ] **Step 3: Verify the script is still valid bash**

Run: `bash -n up.sh`
Expected: no output (no syntax errors).

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml up.sh
git commit -m "chore: remove docker-compose.yml, point up.sh at compose.yaml + dev.compose.yaml"
```

---

### Task 6: Update `CLAUDE.md` and `.env.example`

**Files:**
- Modify: `CLAUDE.md`
- Modify: `.env.example`

**Interfaces:** none — documentation only, describing the end state of Tasks 1-5.

- [ ] **Step 1: Update the Commands section of `CLAUDE.md`**

Find this exact code block:
```
```bash
./up.sh          # docker compose up --build, foreground, prints a ready banner once all services are healthy
./up.sh -d        # same, detached
docker compose down
docker compose logs -f backend   # or: frontend, postgres, chromadb, searxng, firecrawl-api
docker compose restart backend   # after editing backend code (no hot reload — uvicorn runs without --reload)
```
```
Replace it with:
```
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
```

- [ ] **Step 2: Update the `.env` requirement note**

Find:
```
Requires a root `.env` (gitignored, real secrets — see README's Environment Variables table for the full list: `DATABASE_URL`, `GROQ_API_KEY`, `CHROMA_*`, `SEARXNG_BASE_URL`, `FIRECRAWL_API_*`, `ALIBABA_COOKIES`, `JWT_SECRET`, etc.).
```
Replace it with:
```
Requires a root `.env` (gitignored, real secrets — see `.env.example` and README's Environment Variables table for the full list: `DATABASE_URL`, `GROQ_API_KEY`, `CHROMA_*`, `SEARXNG_BASE_URL`, `FIRECRAWL_API_*`, `ALIBABA_COOKIES`, `JWT_SECRET`, etc.). `BACKEND_DOMAIN`/`FRONTEND_DOMAIN` are prod-only (Traefik routing), unused in dev.
```

- [ ] **Step 3: Add the prod domain vars to `.env.example`**

At the end of `.env.example`, append:
```bash

# --- Prod only (Dokploy/Traefik routing) — unused in dev ---
BACKEND_DOMAIN=
FRONTEND_DOMAIN=
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md .env.example
git commit -m "docs: document the dev/prod compose split and Traefik domain vars"
```

---

### Task 7: Verification

**Files:** none (verification only).

- [ ] **Step 1: Validate every compose file combination**

Run each and confirm no YAML parse errors (missing-`.env`/missing-`dokploy-network` warnings are expected and not failures, per Tasks 1/3/4's notes):
```bash
docker compose -f compose.yaml config --quiet
docker compose -f compose.yaml -f dev.compose.yaml config --quiet
docker compose -f compose.yaml -f prod.compose.yaml config --quiet
```

- [ ] **Step 2: Confirm no stray references to the old filenames remain**

Run: `grep -rn "docker-compose.yml" --include="*.sh" --include="*.md" --include="Dockerfile*" . 2>/dev/null | grep -v node_modules | grep -v .git`
Expected: no matches (everything that referenced `docker-compose.yml` — `up.sh`, `CLAUDE.md` — was updated in Tasks 5-6). If `firecrawl/`'s own vendored files mention `docker-compose.yaml` (their own, unrelated file), that's fine — grep for the literal `.yml` extension used by this repo's own file to avoid false positives from the vendored `firecrawl/` tree, and if any do show up, confirm they're inside `firecrawl/` (out of scope, vendored third-party) before treating anything as a finding.

- [ ] **Step 3: If Docker is available and a throwaway `.env` can be created locally (not committed), attempt a real dev boot**

```bash
cp .env.example .env   # fill in at least POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB with placeholder values if no real secrets are available
docker compose -f compose.yaml -f dev.compose.yaml up --build postgres backend frontend --no-deps
```
This is a heavy build (MinerU/PyTorch backend image, Firecrawl skipped via `--no-deps`) — if it's not feasible in your environment (no Docker, no time budget, no `.env`), report that plainly rather than skipping silently; this is the same category of environment limitation noted in the earlier frontend-migration plan's Task 6.

- [ ] **Step 4: Report findings**

No commit for this task (verification only) — report the validation results from Steps 1-3 in your task report.
