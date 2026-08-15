#!/usr/bin/env bash
# Backs up everything needed to hand this app's DATA (not code) to someone
# else: the Postgres database, the ChromaDB vector store volume, the uploaded
# PDF library, and the generated Machine Report PDFs. Produces one
# self-contained .tar.gz in ./backups/ that restore-data.sh can consume.
#
# Usage: ./scripts/backup-data.sh
# Requires: the stack must be up (docker compose ... up) so `postgres` and
# `chromadb` containers are running for pg_dump / volume access.
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE="docker compose -f compose.yaml -f dev.compose.yaml"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
WORKDIR="$(mktemp -d)"
OUT_DIR="./backups"
OUT_FILE="${OUT_DIR}/comfest-data-${TIMESTAMP}.tar.gz"

mkdir -p "$OUT_DIR"
trap 'rm -rf "$WORKDIR"' EXIT

# Read POSTGRES_USER/POSTGRES_DB from .env (fallback to compose defaults).
set -a
# shellcheck disable=SC1091
[ -f .env ] && source .env
set +a
POSTGRES_USER="${POSTGRES_USER:-comfest}"
POSTGRES_DB="${POSTGRES_DB:-comfest_db}"

echo "==> Dumping Postgres ($POSTGRES_DB)..."
$COMPOSE exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom \
  > "$WORKDIR/postgres.dump"

echo "==> Archiving ChromaDB volume..."
# Use a throwaway container to tar the named volume's contents without
# needing the chromadb container itself to expose a shell with tar
# guaranteed present.
docker run --rm \
  -v "$(basename "$(pwd)")_chromadata:/data:ro" \
  -v "$WORKDIR:/backup" \
  alpine sh -c "tar czf /backup/chromadata.tar.gz -C /data ."

PDF_LIBRARY_HOST="/home/dimas/comfest/document"
if [ -d "$PDF_LIBRARY_HOST" ]; then
  echo "==> Archiving PDF library ($PDF_LIBRARY_HOST)..."
  tar czf "$WORKDIR/pdf_library.tar.gz" -C "$PDF_LIBRARY_HOST" .
else
  echo "==> PDF library dir not found at $PDF_LIBRARY_HOST, skipping."
fi

if [ -d "./backend/reports" ]; then
  echo "==> Archiving Machine Report PDFs (backend/reports)..."
  tar czf "$WORKDIR/machine_reports.tar.gz" -C "./backend/reports" .
else
  echo "==> backend/reports not found, skipping."
fi

echo "==> Bundling into $OUT_FILE..."
tar czf "$OUT_FILE" -C "$WORKDIR" .

echo ""
echo "Done: $OUT_FILE ($(du -h "$OUT_FILE" | cut -f1))"
echo ""
echo "This archive contains real user accounts (hashed passwords) and any"
echo "uploaded documents — review before sharing, and share over a private"
echo "channel, not a public link."
