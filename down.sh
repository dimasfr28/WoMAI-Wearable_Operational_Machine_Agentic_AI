#!/usr/bin/env bash
# Wrapper around `docker compose -f compose.yaml -f dev.compose.yaml down` —
# dev.compose.yaml is an override file (references services like `postgres`
# that it doesn't itself define), so it always needs both -f flags together;
# using just one or the other either leaves half the stack running or errors
# out with "depends on undefined service". This script is just those two
# flags, plus any extra args passed straight through (e.g. `./down.sh -v` to
# also remove volumes).
#
# Usage: ./down.sh          (equivalent to: docker compose -f compose.yaml -f dev.compose.yaml down)
#        ./down.sh -v       (also removes volumes — pgdata, chromadata, etc.)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

docker compose -f compose.yaml -f dev.compose.yaml down "$@"
