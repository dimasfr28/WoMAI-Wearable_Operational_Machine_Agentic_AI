# Spec Desain — Pemisahan Docker Compose Dev/Prod (Traefik/Dokploy)

Tanggal: 2026-08-12
Status: disetujui untuk perencanaan implementasi

## Ringkasan

Ganti `docker-compose.yml` tunggal dengan struktur base + override: `compose.yaml` (service bersama, tidak berubah antar environment) plus `dev.compose.yaml` (hot-reload FE+BE via `Dockerfile.dev`) dan `prod.compose.yaml` (Traefik/Dokploy-based via `Dockerfile.prod`). Motivasi: stack ini punya banyak service vendored/third-party (Postgres, ChromaDB, SearXNG, cluster Firecrawl 5-service) yang identik di dev maupun prod dan tidak butuh hot-reload — cuma `backend` dan `frontend` yang perlu build/volume/networking berbeda antar environment.

## Keputusan Utama

| Aspek | Keputusan |
|---|---|
| Struktur compose | Base + override (`compose.yaml` + `dev.compose.yaml`/`prod.compose.yaml`), bukan dua file mandiri penuh — menghindari duplikasi ~150 baris config Firecrawl |
| `docker-compose.yml` lama | Dihapus, diganti `compose.yaml` (berisi service bersama saja: postgres, chromadb, searxng, firecrawl cluster, top-level `networks`/`volumes`) |
| Dockerfile frontend | Multi-stage tunggal (`dev`/`runner` stage) dipecah jadi `frontend/Dockerfile.dev` dan `frontend/Dockerfile.prod` — logic per stage tidak berubah, cuma dipisah file |
| Dockerfile backend | `backend/Dockerfile.prod` = copy persis Dockerfile lama (tanpa perubahan perilaku). `backend/Dockerfile.dev` = sama persis, CMD ditambah `--reload` |
| Backend hot-reload | `dev.compose.yaml` bind-mount `./backend:/app` + `--reload` di uvicorn — bukan mengubah apa yang di-bake ke image |
| Frontend hot-reload | `dev.compose.yaml` bind-mount `./frontend:/app` + anonymous volume `/app/node_modules` dan `/app/.next` (pola yang sudah ada) |
| PDF library volume | Dev: tetap host bind-mount `/home/dimas/comfest/document:/data/pdf_library` seperti sekarang. Prod: named volume `pdf_library:/data/pdf_library` (portable, tidak bergantung path host tertentu) |
| Traefik/Dokploy | Label eksplisit di `prod.compose.yaml` (bukan mengandalkan UI Dokploy men-generate label), pakai env var placeholder `${BACKEND_DOMAIN}`/`${FRONTEND_DOMAIN}`, asumsi konvensi standar Dokploy: network eksternal `dokploy-network`, certResolver `letsencrypt` |
| Port publish prod | `backend`/`frontend` TIDAK publish port ke host di prod — Traefik/Dokploy me-routing lewat docker network via label, bukan host port |
| `up.sh` | Diupdate untuk selalu jalankan `docker compose -f compose.yaml -f dev.compose.yaml ...` sebagai default lokal (bukan dihapus, bukan dibuat script baru) |
| Command prod | Didokumentasikan di CLAUDE.md (`docker compose -f compose.yaml -f prod.compose.yaml up -d --build`), tanpa script wrapper baru |

## File Layout

```
compose.yaml            # base: postgres, chromadb, searxng, firecrawl-* cluster, networks/volumes bersama
dev.compose.yaml        # override: backend + frontend (Dockerfile.dev, hot-reload volumes)
prod.compose.yaml       # override: backend + frontend (Dockerfile.prod, traefik labels, dokploy-network)
backend/Dockerfile.dev
backend/Dockerfile.prod
frontend/Dockerfile.dev
frontend/Dockerfile.prod
```

`docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile` (lama) dihapus.

## `compose.yaml` (base)

Persis isi `docker-compose.yml` saat ini **dikurangi** service `backend` dan `frontend` — `postgres`, `chromadb`, `searxng`, `firecrawl-playwright`, `firecrawl-redis`, `firecrawl-rabbitmq`, `firecrawl-nuq-postgres`, `firecrawl-api`, plus blok `networks:`/`volumes:` top-level, semuanya verbatim tidak berubah (termasuk semua komentar penjelasan yang sudah ada).

## `dev.compose.yaml`

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
      - /home/dimas/comfest/document:/data/pdf_library
    depends_on:
      postgres:
        condition: service_healthy
      firecrawl-api:
        condition: service_started
    ports:
      - "8002:8000"

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.dev
    environment:
      BACKEND_URL: "http://backend:8000"
    volumes:
      - ./frontend:/app
      - /app/node_modules
      - /app/.next
    depends_on:
      - backend
    ports:
      - "3000:3000"
```

## `prod.compose.yaml`

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

No `ports:` published for `backend`/`frontend` in prod — routing happens via Traefik labels over `dokploy-network`, matching how Dokploy's centrally-managed Traefik discovers services (standard Docker-provider label convention). `postgres`/`chromadb`/`searxng`/`firecrawl-api`'s existing host port publishes in `compose.yaml` are untouched (debugging access only, not part of Traefik routing).

## Dockerfile Splits

**`frontend/Dockerfile.dev`** — the `base`→`deps`→`dev` portion of the current multi-stage file:
```dockerfile
# syntax=docker/dockerfile:1
FROM oven/bun:1-alpine
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile
COPY . .
EXPOSE 3000
CMD ["bun", "run", "dev"]
```

**`frontend/Dockerfile.prod`** — the `deps`→`builder`→`runner` portion, logic unchanged:
```dockerfile
# syntax=docker/dockerfile:1
FROM oven/bun:1-alpine AS deps
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

FROM deps AS builder
COPY . .
RUN bun run build

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

**`backend/Dockerfile.prod`** — exact copy of the current `backend/Dockerfile`, renamed, zero behavior change.

**`backend/Dockerfile.dev`** — identical content to `Dockerfile.prod`, except the final line:
```dockerfile
CMD ["bash", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
```
All other layers (apt deps, MinerU model pre-download, etc.) stay identical — the pre-download is still valuable in dev to avoid a slow first parse request; hot reload comes from the volume mount + `--reload`, not from anything removed at build time.

## `up.sh`

Both `docker compose` invocations (foreground and `-d`) and the `wait_for_ready` polling (`docker compose ps`) gain `-f compose.yaml -f dev.compose.yaml`. No other logic changes (noise filtering, ready banner, etc. stay as-is).

## `CLAUDE.md`

- Commands section: the `./up.sh` line's implicit meaning changes to "dev mode by default"; add one new line documenting the prod command: `docker compose -f compose.yaml -f prod.compose.yaml up -d --build`.
- The "Requires a root `.env`" note gains a mention that `BACKEND_DOMAIN`/`FRONTEND_DOMAIN` are prod-only additions.

## `.env.example`

New section appended:
```bash
# --- Prod only (Dokploy/Traefik routing) — unused in dev ---
BACKEND_DOMAIN=
FRONTEND_DOMAIN=
```

## Known Gap (documented, not solved by this change)

`backend_saved` is a named volume in prod, so it starts **empty** on first deploy — `backend/saved/*.pkl` is gitignored, so Dokploy's repo clone won't include the trained model file. Whoever deploys to prod for the first time needs to manually place `best_model.pkl` (and the performance log) into that volume (e.g. `docker cp` into the running container, or seed it via a Dokploy volume mount from a host path). This is an operational step, not something the compose split itself can solve — the same gap would exist with a bind-mount too, since Dokploy's clone never has the `.pkl` either way.

## Out of Scope

- Actual domain names (placeholders only, filled in by whoever deploys).
- Deploying/testing against a real Dokploy instance — this spec only produces the compose files, not a verified live deployment.
- Changing anything about `postgres`/`chromadb`/`searxng`/`firecrawl-*` service definitions — they move file but their content is untouched.
- Solving the `backend_saved` empty-volume gap (documented above, deferred).
