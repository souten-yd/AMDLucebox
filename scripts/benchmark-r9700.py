#!/usr/bin/env python3
"""Run a repeatable OpenAI-compatible R9700 throughput acceptance smoke."""

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
from typing import Any

DEFAULT_PROMPTS = [
    "Write a Python function that returns the nth Fibonacci number.",
    "Implement binary search over a sorted list and explain its complexity.",
    "Write a function that validates balanced parentheses in a string.",
]


def request_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[dict[str, Any], float]:
    body = json.dumps(payload).encode()
    request = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise RuntimeError("response is not a JSON object")
    return result, time.perf_counter() - start


def optional_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def parse_response(response: dict[str, Any], elapsed: float, prompt: str) -> dict[str, Any]:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        raise RuntimeError("response has no usage object")
    completion_tokens = usage.get("completion_tokens")
    if isinstance(completion_tokens, bool) or not isinstance(completion_tokens, int) or completion_tokens <= 0:
        raise RuntimeError("response has no positive usage.completion_tokens")
    if elapsed <= 0:
        raise RuntimeError("client elapsed time is not positive")
    timings = usage.get("timings")
    if not isinstance(timings, dict):
        timings = {}
    spec_decode_ran = usage.get("spec_decode_ran")
    if not isinstance(spec_decode_ran, bool):
        spec_decode_ran = None
    return {
        "prompt": prompt,
        "completion_tokens": completion_tokens,
        "client_elapsed_seconds": elapsed,
        "client_e2e_tokens_per_second": completion_tokens / elapsed,
        "server_decode_tokens_per_second": optional_number(timings.get("decode_tokens_per_sec")),
        "prefill_milliseconds": optional_number(timings.get("prefill_ms")),
        "decode_milliseconds": optional_number(timings.get("decode_ms")),
        "speculative_decode_ran": spec_decode_ran,
        "acceptance_rate": optional_number(usage.get("accept_rate")),
    }


def summarize_runs(
    runs: list[dict[str, Any]],
    pass_tps: float,
    fail_tps: float,
    reference_tps: float | None = None,
    max_regression_percent: float = 10.0,
) -> tuple[dict[str, Any], str, list[str]]:
    if not runs:
        raise ValueError("at least one measured run is required")
    server_rates = [run["server_decode_tokens_per_second"] for run in runs]
    client_rates = [float(run["client_e2e_tokens_per_second"]) for run in runs]
    acceptance_rates = [run["acceptance_rate"] for run in runs if run["acceptance_rate"] is not None]
    speculative_count = sum(run["speculative_decode_ran"] is True for run in runs)
    reasons: list[str] = []

    if any(rate is None or rate <= 0 for rate in server_rates):
        average_server = None
        status = "fail"
        reasons.append("one or more requests lacked positive server decode throughput")
    else:
        average_server = statistics.mean(float(rate) for rate in server_rates)
        status = "pass" if average_server >= pass_tps else "warn" if average_server >= fail_tps else "fail"
        if status == "fail":
            reasons.append("average server decode throughput was below the fail threshold")

    if speculative_count != len(runs):
        status = "fail"
        reasons.append("speculative decode did not run for every measured request")

    aggregate: dict[str, Any] = {
        "average_server_decode_tokens_per_second": average_server,
        "average_client_e2e_tokens_per_second": statistics.mean(client_rates),
        "average_acceptance_rate": statistics.mean(float(rate) for rate in acceptance_rates) if acceptance_rates else None,
        "acceptance_rate_reported_count": len(acceptance_rates),
        "speculative_decode_request_count": speculative_count,
        "speculative_decode_request_fraction": speculative_count / len(runs),
        "measured_request_count": len(runs),
    }

    if reference_tps is not None:
        if reference_tps <= 0:
            raise ValueError("reference server decode throughput must be positive")
        regression = None if average_server is None else 100.0 * (reference_tps - average_server) / reference_tps
        passed = regression is not None and regression <= max_regression_percent
        aggregate["reference_comparison"] = {
            "reference_server_decode_tokens_per_second": reference_tps,
            "regression_percent": regression,
            "max_regression_percent": max_regression_percent,
            "passed": passed,
        }
        if not passed:
            status = "fail"
            reasons.append("candidate exceeded the maximum Reference regression")
    return aggregate, status, reasons


def load_reference_server_tps(path: str) -> float:
    reference = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        value = reference["aggregate"]["average_server_decode_tokens_per_second"]
    except (KeyError, TypeError) as error:
        raise ValueError("Reference JSON has no aggregate server decode throughput") from error
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError("Reference JSON server decode throughput is not positive")
    return float(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8216")
    parser.add_argument("--output", default="benchmark-r9700.json")
    parser.add_argument("--prompts-json")
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--pass-tps", type=float, default=180.0)
    parser.add_argument("--fail-tps", type=float, default=170.0)
    parser.add_argument("--reference-results")
    parser.add_argument("--max-regression-percent", type=float, default=10.0)
    args = parser.parse_args()
    if args.fail_tps > args.pass_tps:
        parser.error("--fail-tps must not exceed --pass-tps")
    if args.max_tokens <= 0 or args.warmups < 0:
        parser.error("--max-tokens must be positive and --warmups cannot be negative")
    prompts = DEFAULT_PROMPTS
    if args.prompts_json:
        prompts = json.loads(Path(args.prompts_json).read_text(encoding="utf-8"))
        if not isinstance(prompts, list) or not prompts or not all(isinstance(p, str) for p in prompts):
            parser.error("prompts JSON must be a non-empty string array")

    payload: dict[str, Any] = {"prompt": "", "max_tokens": args.max_tokens, "temperature": 0}
    endpoint = f"{args.base_url.rstrip('/')}/v1/completions"
    runs: list[dict[str, Any]] = []
    try:
        for index in range(args.warmups):
            payload["prompt"] = prompts[index % len(prompts)]
            request_json(endpoint, payload, args.timeout)
        for prompt in prompts:
            payload["prompt"] = prompt
            response, elapsed = request_json(endpoint, payload, args.timeout)
            runs.append(parse_response(response, elapsed, prompt))
        reference_tps = load_reference_server_tps(args.reference_results) if args.reference_results else None
        aggregate, status, reasons = summarize_runs(
            runs, args.pass_tps, args.fail_tps, reference_tps, args.max_regression_percent
        )
    except (OSError, urllib.error.HTTPError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"benchmark failed: {error}", file=sys.stderr)
        return 2

    result = {
        "schema_version": 2,
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "primary_measurement": "server_decode_tokens_per_second",
        "settings": {
            "max_tokens": args.max_tokens,
            "warmup_request_count": args.warmups,
            "thresholds": {"pass": args.pass_tps, "fail_below": args.fail_tps},
            "max_reference_regression_percent": args.max_regression_percent,
        },
        "aggregate": aggregate,
        "status": status,
        "failure_reasons": reasons,
        "runs": runs,
    }
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    server_average = aggregate["average_server_decode_tokens_per_second"]
    server_text = "missing" if server_average is None else f"{server_average:.1f}"
    print(
        f"server decode {server_text} tok/s; "
        f"client E2E {aggregate['average_client_e2e_tokens_per_second']:.1f} tok/s: {status.upper()}"
    )
    return 1 if status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
