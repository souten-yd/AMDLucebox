#!/usr/bin/env python3
"""Verify staged model weights against the external acceptance manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(
    manifest_path: Path,
    model_dir: Path,
    build_info_path: Path,
    expected_rocm: str,
) -> dict[str, Any]:
    manifest = load_object(manifest_path)
    build_info = load_object(build_info_path)
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported model manifest schema")
    conversion = manifest.get("conversion")
    if not isinstance(conversion, dict):
        raise ValueError("model manifest has no conversion object")
    upstream = conversion.get("upstream_commit")
    if upstream != build_info.get("upstream_commit"):
        raise ValueError("model conversion and release upstream commits differ")
    if build_info.get("llvm_target") != "gfx1201":
        raise ValueError("release build is not for gfx1201")
    if build_info.get("rocm_version") != expected_rocm:
        raise ValueError("release build ROCm version does not match selected track")

    models = manifest.get("production_models")
    if not isinstance(models, list) or {item.get("role") for item in models if isinstance(item, dict)} != {
        "target",
        "draft",
    }:
        raise ValueError("model manifest must contain exactly target and draft roles")
    if len(models) != 2:
        raise ValueError("model manifest must contain exactly two production models")

    verified: list[dict[str, Any]] = []
    resolved_root = model_dir.resolve(strict=True)
    for item in models:
        if not isinstance(item, dict):
            raise ValueError("production model entry is not an object")
        filename = item.get("filename")
        expected_size = item.get("size_bytes")
        expected_hash = item.get("sha256")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError("production model filename must be a basename")
        if not isinstance(expected_size, int) or expected_size <= 0:
            raise ValueError(f"invalid size for {filename}")
        if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
            raise ValueError(f"invalid SHA-256 for {filename}")
        path = model_dir / filename
        if path.is_symlink() or not path.is_file() or path.parent.resolve() != resolved_root:
            raise ValueError(f"model is not a regular in-root file: {filename}")
        actual_size = path.stat().st_size
        actual_hash = sha256_file(path)
        if actual_size != expected_size:
            raise ValueError(f"size mismatch for {filename}")
        if actual_hash != expected_hash:
            raise ValueError(f"SHA-256 mismatch for {filename}")
        verified.append(
            {
                "role": item["role"],
                "filename": filename,
                "size_bytes": actual_size,
                "sha256": actual_hash,
                "repository": item.get("repository"),
                "repository_revision": item.get("repository_revision"),
            }
        )

    return {
        "schema_version": 1,
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_filename": manifest_path.name,
        "manifest_sha256": sha256_file(manifest_path),
        "build_info_sha256": sha256_file(build_info_path),
        "upstream_commit": upstream,
        "rocm_build_version": expected_rocm,
        "llvm_target": "gfx1201",
        "models": verified,
        "status": "pass",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--build-info", required=True, type=Path)
    parser.add_argument("--expected-rocm", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.manifest, args.model_dir, args.build_info, args.expected_rocm)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"model verification failed: {error}\n")
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"verified {len(result['models'])} staged models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
