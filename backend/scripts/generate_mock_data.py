"""Generate mock/demo sensor data — the ONLY way to create simulated data
now (see MODE in app/config.py). Requires the backend to be running with
MODE=mock in .env; POST /sensor/mock/generate itself runs synchronously
(writes `count` readings then returns in one request-response cycle, no
background thread/scheduled process — see routes_sensor.py).

Run manually: `docker compose exec backend python scripts/generate_mock_data.py <machine_id> [--count N] [--interval-minutes M]`

Deliberately an HTTP call to the ALREADY-RUNNING backend process on
localhost (port 8000 — the container-internal uvicorn port, NOT the
host-mapped 8002 from dev.compose.yaml), not a direct import of the
generator function — running it in-process here would still work, but
going through the real endpoint also exercises the MODE=mock gate exactly
as any other caller would.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

BASE_URL = "http://localhost:8000"


def generate(machine_id: str, count: int, interval_minutes: float) -> None:
    url = (
        f"{BASE_URL}/sensor/mock/generate"
        f"?machine_id={machine_id}&count={count}&interval_minutes={interval_minutes}"
    )
    req = urllib.request.Request(url, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            print(json.dumps(json.loads(resp.read()), indent=2))
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode()}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(
            f"Could not reach {BASE_URL} — is the backend running? ({exc.reason})",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("machine_id")
    parser.add_argument("--count", type=int, default=10, help="Number of readings to generate (default: 10)")
    parser.add_argument(
        "--interval-minutes",
        type=float,
        default=2.0,
        help="Simulated spacing between readings, oldest to newest (default: 2.0)",
    )
    args = parser.parse_args()
    generate(args.machine_id, args.count, args.interval_minutes)


if __name__ == "__main__":
    main()
