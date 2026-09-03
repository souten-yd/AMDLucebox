#!/usr/bin/env python3
"""Write timestamped amd-smi metric samples as JSON Lines until terminated."""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

running = True


def redact_hardware_identifiers(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: "REDACTED" if any(token in key.lower() for token in ("serial", "uuid", "unique_id"))
            else redact_hardware_identifiers(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_hardware_identifiers(item) for item in value]
    return value


def stop(_signum: int, _frame: object) -> None:
    global running
    running = False


def read_metric() -> dict[str, object]:
    completed = subprocess.run(
        ["amd-smi", "metric", "--json"], text=True, capture_output=True, timeout=30, check=False
    )
    sample: dict[str, object] = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "returncode": completed.returncode,
    }
    if completed.returncode == 0:
        try:
            sample["gpu_data"] = redact_hardware_identifiers(json.loads(completed.stdout))
        except json.JSONDecodeError:
            sample["error"] = "amd-smi returned invalid JSON"
    else:
        sample["error"] = completed.stderr.strip()
    return sample


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be positive")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    failures = 0
    with args.output.open("w", encoding="utf-8") as stream:
        while running:
            sample = read_metric()
            if sample["returncode"] != 0 or "error" in sample:
                failures += 1
            stream.write(json.dumps(sample, sort_keys=True) + "\n")
            stream.flush()
            deadline = time.monotonic() + args.interval
            while running and time.monotonic() < deadline:
                time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
