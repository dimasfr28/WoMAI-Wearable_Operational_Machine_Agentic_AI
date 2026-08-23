#!/usr/bin/env bash
# Wrapper around `docker compose -f compose.yaml -f dev.compose.yaml up` that:
#   1. Still shows the full build log (nothing hidden during image builds).
#   2. Filters out the noisy Firecrawl nuq-postgres pg_cron housekeeping
#      lines once containers are running (they repeat every few seconds and
#      drown out anything else in the log).
#   3. Prints a clear "ALL SERVICES READY" banner once every service with a
#      healthcheck reports healthy (and every service without one is running).
#
# Usage: ./up_no_build.sh          (equivalent to: docker compose -f compose.yaml -f dev.compose.yaml up)
#        ./up_no_build.sh -d       (detached — still prints the ready banner, then returns)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# Lines to drop once we're past the build phase (pg_cron job spam from
# firecrawl-nuq-postgres — see compose.yaml comment on its healthcheck).
NOISE_PATTERN='cron job [0-9]+ (starting|completed|COMMAND completed)'

wait_for_ready() {
  # Poll `docker compose ps` until every service is either "healthy" (has a
  # healthcheck) or "running" (no healthcheck defined), then print the banner.
  local all_ready
  for _ in $(seq 1 180); do  # ~15 min ceiling (5s * 180)
    local rows
    rows="$(docker compose -f compose.yaml -f dev.compose.yaml ps --format '{{.Service}} {{.State}} {{.Health}}' 2>/dev/null || true)"
    if [ -z "$rows" ]; then
      sleep 5
      continue
    fi
    all_ready=true
    while read -r svc state health; do
      [ -z "$svc" ] && continue
      if [ "$state" != "running" ]; then
        all_ready=false
        break
      fi
      # health is empty for services with no healthcheck -> treat as ready.
      if [ -n "$health" ] && [ "$health" != "healthy" ]; then
        all_ready=false
        break
      fi
    done <<< "$rows"
    if [ "$all_ready" = true ]; then
      echo ""
      echo "=================================================="
      echo " ALL SERVICES READY — frontend: http://localhost:3002"
      echo "                       backend docs: http://localhost:8002/docs"
      echo "=================================================="
      return 0
    fi
    sleep 5
  done
  echo ""
  echo "WARNING: timed out waiting for all services to become healthy/running (see 'docker compose ps')."
}

if [[ "${1:-}" == "-d" ]]; then
  docker compose -f compose.yaml -f dev.compose.yaml up -d
  wait_for_ready
  exit 0
fi

# Foreground mode: run the ready-check in the background against the compose
# project while streaming (and filtering) the live log in the foreground.
wait_for_ready &
READY_PID=$!
trap 'kill "$READY_PID" 2>/dev/null || true' EXIT

docker compose -f compose.yaml -f dev.compose.yaml up 2>&1 | grep -vE "$NOISE_PATTERN"