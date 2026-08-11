# syntax=docker/dockerfile:1

# ============================================================
# Frontend (Next.js) - multi-stage Dockerfile (Bun)
#   - target "dev"    : dev server dengan hot-reload (compose.dev.yaml)
#   - target "runner" : production image minimal (compose.prod.yaml)
# ============================================================

FROM oven/bun:1-alpine AS base
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

# ---------- dependencies ----------
FROM base AS deps
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

# ---------- development ----------
FROM deps AS dev
COPY . .
EXPOSE 3000
CMD ["bun", "run", "dev"]

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
