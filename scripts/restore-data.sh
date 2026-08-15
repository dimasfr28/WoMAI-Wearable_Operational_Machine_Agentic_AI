#!/usr/bin/env bash
# Restores a data bundle produced by backup-data.sh: Postgres database,
# ChromaDB volume, PDF library, and Machine Report PDFs.
#
# Usage: ./scripts/restore-data.sh path/to/comfest-data-YYYYMMDD-HHMMSS.tar.gz
#
# WARNING: this OVERWRITES the current Postgres database (POSTGRES_DB) and
# the ChromaDB volume's contents. Run this only on a fresh setup or one
# you're OK discarding.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ $# -ne 1 ]; then
  echo "Usage: $0 path/to/comfest-data-*.tar.gz" >&2
  exit 1
fi
ARCHIVE="$1"
[ -f "$ARCHIVE" ] || { echo "File not found: $ARCHIVE" >&2; exit 1; }

COMPOSE="docker compose -f compose.yaml -f dev.compose.yaml"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

echo "==> Extracting $ARCHIVE..."
tar xzf "$ARCHIVE" -C "$WORKDIR"

set -a
# shellcheck disable=SC1091
[ -f .env ] && source .env
set +a
POSTGRES_USER="${POSTGRES_USER:-comfest}"
POSTGRES_DB="${POSTGRES_DB:-comfest_db}"

read -r -p "This will OVERWRITE the current '$POSTGRES_DB' database and ChromaDB data. Continue? [y/N] " CONFIRM
[ "$CONFIRM" = "y" ] || [ "$CONFIRM" = "Y" ] || { echo "Aborted."; exit 1; }

echo "==> Making sure postgres and chromadb are up..."
$COMPOSE up -d postgres chromadb
$COMPOSE exec -T postgres sh -c 'until pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; do sleep 1; done'

if [ -f "$WORKDIR/postgres.dump" ]; then
  echo "==> Restoring Postgres..."
  $COMPOSE exec -T postgres dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"
  $COMPOSE exec -T postgres createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
  $COMPOSE exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --role="$POSTGRES_USER" \
    < "$WORKDIR/postgres.dump"
else
  echo "==> No postgres.dump in archive, skipping."
fi

if [ -f "$WORKDIR/chromadata.tar.gz" ]; then
  echo "==> Restoring ChromaDB volume..."
  $COMPOSE stop chromadb
  docker run --rm \
    -v "$(basename "$(pwd)")_chromadata:/data" \
    -v "$WORKDIR:/backup" \
    alpine sh -c "rm -rf /data/* /data/..?* /data/.[!.]* 2>/dev/null; tar xzf /backup/chromadata.tar.gz -C /data"
  $COMPOSE start chromadb
else
  echo "==> No chromadata.tar.gz in archive, skipping."
fi

PDF_LIBRARY_HOST="/home/dimas/comfest/document"
if [ -f "$WORKDIR/pdf_library.tar.gz" ]; then
  echo "==> Restoring PDF library to $PDF_LIBRARY_HOST..."
  mkdir -p "$PDF_LIBRARY_HOST"
  tar xzf "$WORKDIR/pdf_library.tar.gz" -C "$PDF_LIBRARY_HOST"
else
  echo "==> No pdf_library.tar.gz in archive, skipping."
fi

if [ -f "$WORKDIR/machine_reports.tar.gz" ]; then
  echo "==> Restoring Machine Report PDFs to backend/reports..."
  mkdir -p "./backend/reports"
  tar xzf "$WORKDIR/machine_reports.tar.gz" -C "./backend/reports"
else
  echo "==> No machine_reports.tar.gz in archive, skipping."
fi

echo ""
echo "Done. Restart the backend so it picks up the restored data cleanly:"
echo "  $COMPOSE restart backend"
