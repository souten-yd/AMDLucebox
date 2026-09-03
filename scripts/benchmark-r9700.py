#!/usr/bin/env python3
"""Run a repeatable OpenAI-compatible completion throughput smoke."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PROMPTS = [
    "Write a Python function that returns the nth Fibonacci number.",
    "Implement binary search over a sorted list and explain its complexity.",
    "Write a function that validates balanced parentheses in a string.",
]


def request_json(url: str, payload: dict, timeout: float) -> tuple[dict, float]:
    body = json.dumps(payload).encode()
    request = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.load(response)
    return result, time.perf_counter() - start


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8216")
    parser.add_argument("--output", default="benchmark-r9700.json")
    parser.add_argument("--prompts-json")
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--pass-tps", type=float, default=180.0)
    parser.add_argument("--fail-tps", type=float, default=170.0)
    parser.add_argument("--reference-results")
    parser.add_argument("--max-regression-percent", type=float, default=10.0)
    args = parser.parse_args()
    if args.fail_tps > args.pass_tps:
        parser.error("--fail-tps must not exceed --pass-tps")
    prompts = DEFAULT_PROMPTS
    if args.prompts_json:
        prompts = json.loads(Path(args.prompts_json).read_text(encoding="utf-8"))
        if not isinstance(prompts, list) or not prompts or not all(isinstance(p, str) for p in prompts):
            parser.error("prompts JSON must be a non-empty string array")

    runs = []
    try:
        for prompt in prompts:
            response, elapsed = request_json(
                f"{args.base_url.rstrip('/')}/v1/completions",
                {"prompt": prompt, "max_tokens": args.max_tokens, "temperature": 0},
                args.timeout,
            )
            completion_tokens = response.get("usage", {}).get("completion_tokens")
            if not isinstance(completion_tokens, int) or completion_tokens <= 0:
                raise RuntimeError("response has no positive usage.completion_tokens")
            runs.append({
                "prompt": prompt,
                "completion_tokens": completion_tokens,
                "elapsed_seconds": elapsed,
                "tokens_per_second": completion_tokens / elapsed,
            })
    except (OSError, urllib.error.HTTPError, ValueError, RuntimeError) as error:
        print(f"benchmark failed: {error}", file=sys.stderr)
        return 2

    average = statistics.mean(run["tokens_per_second"] for run in runs)
    status = "pass" if average >= args.pass_tps else "warn" if average >= args.fail_tps else "fail"
    result = {
        "schema_version": 1,
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "measurement": "client_end_to_end_completion_tokens_per_second",
        "average_tokens_per_second": average,
        "thresholds": {"pass": args.pass_tps, "fail_below": args.fail_tps},
        "status": status,
        "runs": runs,
    }
    if args.reference_results:
        reference = json.loads(Path(args.reference_results).read_text(encoding="utf-8"))
        reference_tps = float(reference["average_tokens_per_second"])
        regression = 100.0 * (reference_tps - average) / reference_tps
        result["reference_comparison"] = {
            "reference_tokens_per_second": reference_tps,
            "regression_percent": regression,
            "max_regression_percent": args.max_regression_percent,
            "passed": regression <= args.max_regression_percent,
        }
        if regression > args.max_regression_percent:
            status = result["status"] = "fail"
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{average:.1f} tok/s: {status.upper()}")
    return 1 if status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
