#!/usr/bin/env python3
"""Fail-closed verification for metadata-only Stable promotion."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REFERENCE_FILES = (
    "benchmark-reference.json",
    "benchmark-reference.server.log",
    "environment-before.json",
    "environment-after.json",
    "model-manifest.json",
    "model-verification.json",
    "validation-context.json",
    "release-BUILD_INFO.json",
    "release-SHA256SUMS",
    "release-asset.sha256",
    "runtime-ldd.txt",
    "r9700-diagnostics/hip-smoke.txt",
    "r9700-diagnostics/hipcc-version.txt",
)

CANDIDATE_FILES = (
    "benchmark-candidate.json",
    "benchmark-candidate.server.log",
    "environment-before.json",
    "environment-after.json",
    "model-manifest.json",
    "model-verification.json",
    "validation-context.json",
    "release-BUILD_INFO.json",
    "release-SHA256SUMS",
    "release-asset.sha256",
    "runtime-ldd.txt",
    "runtime-selection.json",
    "reference-candidate-input-check.json",
    "r9700-diagnostics/hip-smoke.txt",
    "r9700-diagnostics/hipcc-version.txt",
)

SECRET_PATTERNS = (
    re.compile(rb"ghp_[A-Za-z0-9]{20,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"authorization\s*:\s*(?:bearer|token)\s+\S+", re.IGNORECASE),
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_files(root: Path, names: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        path = root / name
        if not path.is_file():
            raise ValueError(f"required evidence is missing: {path}")
        data = path.read_bytes()
        if any(pattern.search(data) for pattern in SECRET_PATTERNS):
            raise ValueError(f"possible credential found in evidence: {path}")
        result[name] = hashlib.sha256(data).hexdigest()
    return result


def normalize_models(value: dict[str, Any]) -> list[dict[str, Any]]:
    keys = ("role", "filename", "size_bytes", "sha256", "repository", "repository_revision")
    models = value.get("models")
    if not isinstance(models, list):
        raise ValueError("model verification has no models array")
    return sorted(({key: item.get(key) for key in keys} for item in models), key=lambda item: item["role"])


def validate_run(run: dict[str, Any], expected_id: int, expected_head: str) -> None:
    if run.get("databaseId") != expected_id:
        raise ValueError(f"workflow run ID mismatch: expected {expected_id}")
    if run.get("conclusion") != "success" or run.get("event") != "workflow_dispatch":
        raise ValueError(f"workflow run {expected_id} was not a successful manual run")
    if run.get("headBranch") != "main" or run.get("headSha") != expected_head:
        raise ValueError(f"workflow run {expected_id} is not the recorded trusted main commit")


def expected_release_assets(
    release: dict[str, Any],
    assets_dir: Path,
    expected_hashes: dict[str, str],
) -> dict[str, dict[str, Any]]:
    if release.get("isDraft") is not False or release.get("isPrerelease") is not True:
        raise ValueError("release must be a published prerelease before promotion")
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ValueError("release metadata has no assets array")
    by_name = {item.get("name"): item for item in assets}
    if set(by_name) != set(expected_hashes):
        raise ValueError("release has unexpected or missing pre-promotion assets")
    result: dict[str, dict[str, Any]] = {}
    for name, expected_hash in expected_hashes.items():
        path = assets_dir / name
        if not path.is_file():
            raise ValueError(f"downloaded release asset is missing: {name}")
        actual_hash = sha256(path)
        metadata = by_name[name]
        if actual_hash != expected_hash or metadata.get("digest") != f"sha256:{expected_hash}":
            raise ValueError(f"release asset hash mismatch: {name}")
        if metadata.get("size") != path.stat().st_size:
            raise ValueError(f"release asset size mismatch: {name}")
        result[name] = {
            "id": metadata.get("id"),
            "size_bytes": path.stat().st_size,
            "sha256": actual_hash,
            "created_at": metadata.get("createdAt"),
            "updated_at": metadata.get("updatedAt"),
        }
    sums = (assets_dir / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    parsed = {line.split(maxsplit=1)[1].lstrip(" *"): line.split(maxsplit=1)[0] for line in sums if len(line.split(maxsplit=1)) == 2}
    for name, expected_hash in expected_hashes.items():
        if name != "SHA256SUMS" and parsed.get(name) != expected_hash:
            raise ValueError(f"SHA256SUMS does not authenticate {name}")
    return result


def verify(args: argparse.Namespace) -> dict[str, Any]:
    release = load_json(args.release_json)
    if release.get("tagName") != args.tag:
        raise ValueError("release tag mismatch")

    reference_context = load_json(args.reference_dir / "validation-context.json")
    candidate_context = load_json(args.candidate_dir / "validation-context.json")
    reference_benchmark = load_json(args.reference_dir / "benchmark-reference.json")
    candidate_benchmark = load_json(args.candidate_dir / "benchmark-candidate.json")
    reference_models = load_json(args.reference_dir / "model-verification.json")
    candidate_models = load_json(args.candidate_dir / "model-verification.json")
    reference_environment = load_json(args.reference_dir / "environment-before.json")
    candidate_environment = load_json(args.candidate_dir / "environment-before.json")
    runtime_selection = load_json(args.candidate_dir / "runtime-selection.json")
    input_check = load_json(args.candidate_dir / "reference-candidate-input-check.json")
    reference_run = load_json(args.reference_run_json)
    candidate_run = load_json(args.candidate_run_json)

    validate_run(reference_run, args.reference_run_id, reference_context.get("workflow_head_sha"))
    validate_run(candidate_run, args.candidate_run_id, candidate_context.get("workflow_head_sha"))
    for label, context, expected_track, expected_run in (
        ("Reference", reference_context, "reference", args.reference_run_id),
        ("Candidate", candidate_context, "candidate", args.candidate_run_id),
    ):
        if context.get("release_tag") != args.tag or context.get("track") != expected_track:
            raise ValueError(f"{label} context does not identify the release and track")
        if str(context.get("workflow_run_id")) != str(expected_run):
            raise ValueError(f"{label} context run ID mismatch")
    if candidate_context.get("reference_run_id") != str(args.reference_run_id):
        raise ValueError("Candidate context does not identify the accepted Reference run")

    if reference_benchmark.get("status") != "pass" or candidate_benchmark.get("status") != "pass":
        raise ValueError("both benchmark results must be PASS")
    if reference_benchmark.get("failure_reasons") or candidate_benchmark.get("failure_reasons"):
        raise ValueError("benchmark result contains failure reasons")
    comparison = candidate_benchmark.get("aggregate", {}).get("reference_comparison", {})
    reference_tps = reference_benchmark.get("aggregate", {}).get("average_server_decode_tokens_per_second")
    candidate_tps = candidate_benchmark.get("aggregate", {}).get("average_server_decode_tokens_per_second")
    if comparison.get("passed") is not True or comparison.get("max_regression_percent") != 10.0:
        raise ValueError("Candidate 10% Reference regression gate did not pass")
    if comparison.get("reference_server_decode_tokens_per_second") != reference_tps:
        raise ValueError("Candidate comparison used a different Reference throughput")
    if not isinstance(reference_tps, (int, float)) or reference_tps < 120.0:
        raise ValueError("Reference is below the operator-approved production floor")
    if not isinstance(candidate_tps, (int, float)) or candidate_tps < 120.0:
        raise ValueError("Candidate is below the operator-approved production floor")
    for label, benchmark in (("Reference", reference_benchmark), ("Candidate", candidate_benchmark)):
        aggregate = benchmark.get("aggregate", {})
        if aggregate.get("speculative_decode_request_fraction") != 1.0:
            raise ValueError(f"{label} did not use speculative decode on every request")
        if benchmark.get("settings", {}).get("prompt_count") != 10:
            raise ValueError(f"{label} did not use the ten-prompt corpus")

    if reference_context.get("benchmark") != candidate_context.get("benchmark"):
        raise ValueError("Reference and Candidate benchmark settings differ")
    if reference_context.get("server") != candidate_context.get("server"):
        raise ValueError("Reference and Candidate server settings differ")
    if reference_context.get("hip_visible_devices") != candidate_context.get("hip_visible_devices"):
        raise ValueError("Reference and Candidate GPU selection differs")
    if reference_models.get("status") != "pass" or candidate_models.get("status") != "pass":
        raise ValueError("model verification did not pass")
    normalized_models = normalize_models(reference_models)
    if normalized_models != normalize_models(candidate_models):
        raise ValueError("Reference and Candidate model identities differ")
    if input_check.get("status") != "pass" or input_check.get("model_identity_match") is not True:
        raise ValueError("Reference/Candidate input identity check did not pass")

    if not str(reference_environment.get("rocm_userspace_version", "")).startswith("7.2."):
        raise ValueError("Reference environment is not ROCm 7.2.x")
    if candidate_environment.get("rocm_userspace_version") != "10.0.0":
        raise ValueError("Candidate environment is not ROCm 10.0.0")
    if reference_environment.get("status") != "pass" or candidate_environment.get("status") != "pass":
        raise ValueError("environment capture did not pass")
    if runtime_selection.get("status") != "pass" or runtime_selection.get("rocm_userspace_version") != "10.0.0":
        raise ValueError("Candidate runtime selection did not pass")
    if runtime_selection.get("source_image_digest") != candidate_context.get("rocm_runtime_source_digest"):
        raise ValueError("Candidate runtime source digest differs across evidence")

    reference_asset = reference_context["release_asset_name"]
    candidate_asset = candidate_context["release_asset_name"]
    expected_hashes = {
        reference_asset: args.reference_asset_sha256,
        candidate_asset: args.candidate_asset_sha256,
        "SHA256SUMS": args.checksums_sha256,
    }
    original_assets = expected_release_assets(release, args.assets_dir, expected_hashes)
    for root, expected_hash in (
        (args.reference_dir, args.reference_asset_sha256),
        (args.candidate_dir, args.candidate_asset_sha256),
    ):
        recorded = (root / "release-asset.sha256").read_text(encoding="utf-8").split()[0]
        if recorded != expected_hash:
            raise ValueError(f"validation evidence used a different release asset: {root}")

    evidence_files = {
        **{f"reference/{name}": digest for name, digest in require_files(args.reference_dir, REFERENCE_FILES).items()},
        **{f"candidate/{name}": digest for name, digest in require_files(args.candidate_dir, CANDIDATE_FILES).items()},
        "reference-run.json": sha256(args.reference_run_json),
        "candidate-run.json": sha256(args.candidate_run_json),
    }
    return {
        "schema_version": 1,
        "status": "pass",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "release": {"tag": args.tag, "url": release.get("url"), "original_assets": original_assets},
        "validation": {
            "reference_run_id": args.reference_run_id,
            "candidate_run_id": args.candidate_run_id,
            "reference_server_decode_tokens_per_second": reference_tps,
            "candidate_server_decode_tokens_per_second": candidate_tps,
            "candidate_regression_percent": comparison.get("regression_percent"),
            "candidate_regression_gate_passed": True,
            "models": normalized_models,
            "prompt_corpus_sha256": reference_context["benchmark"]["prompt_corpus_sha256"],
            "reference_rocm_userspace": reference_environment["rocm_userspace_version"],
            "candidate_rocm_userspace": candidate_environment["rocm_userspace_version"],
            "candidate_runtime_source_digest": runtime_selection["source_image_digest"],
        },
        "evidence_files": evidence_files,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--release-json", required=True, type=Path)
    parser.add_argument("--assets-dir", required=True, type=Path)
    parser.add_argument("--reference-dir", required=True, type=Path)
    parser.add_argument("--candidate-dir", required=True, type=Path)
    parser.add_argument("--reference-run-json", required=True, type=Path)
    parser.add_argument("--candidate-run-json", required=True, type=Path)
    parser.add_argument("--reference-run-id", required=True, type=int)
    parser.add_argument("--candidate-run-id", required=True, type=int)
    parser.add_argument("--reference-asset-sha256", required=True)
    parser.add_argument("--candidate-asset-sha256", required=True)
    parser.add_argument("--checksums-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = verify(args)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"promotion verification failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
