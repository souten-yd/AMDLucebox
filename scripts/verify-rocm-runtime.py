#!/usr/bin/env python3
"""Verify a staged ROCm userspace before trusted R9700 validation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def version_family(version: str) -> tuple[str, str]:
    parts = version.split(".")
    if len(parts) < 2 or not all(part.isdigit() for part in parts[:2]):
        raise ValueError(f"invalid ROCm version: {version}")
    return parts[0], parts[1]


def verify(
    runtime_root: Path,
    track: str,
    matrix_path: Path,
    provenance_path: Path | None,
) -> dict[str, Any]:
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    try:
        expected = next(item for item in matrix["tracks"] if item["name"] == track)
    except (KeyError, StopIteration, TypeError) as error:
        raise ValueError(f"track is absent from build matrix: {track}") from error

    runtime_root = runtime_root.resolve()
    version_path = runtime_root / ".info/version"
    required = [
        version_path,
        runtime_root / "bin/hipcc",
        runtime_root / "bin/rocminfo",
        runtime_root / "bin/amd-smi",
        runtime_root / "bin/rocm-smi",
        runtime_root / "lib/libamdhip64.so.7",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise ValueError("runtime is missing required paths: " + ", ".join(missing))

    actual_version = version_path.read_text(encoding="utf-8").strip()
    expected_version = str(expected["rocm_version"])
    if track == "candidate":
        if actual_version != expected_version:
            raise ValueError(
                f"Candidate requires exact ROCm {expected_version} userspace, got {actual_version}"
            )
        if provenance_path is None:
            raise ValueError("Candidate requires a staged runtime provenance manifest")
    elif version_family(actual_version) != version_family(expected_version):
        raise ValueError(
            f"Reference requires ROCm {'.'.join(version_family(expected_version))}.x userspace, "
            f"got {actual_version}"
        )

    provenance: dict[str, Any] | None = None
    verified_files: list[dict[str, Any]] = []
    if provenance_path is not None:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        if provenance.get("source_manifest_digest") != expected["image_digest"]:
            raise ValueError("runtime source image digest differs from the build matrix")
        if provenance.get("runtime_version") != actual_version:
            raise ValueError("runtime provenance version differs from staged userspace")
        if Path(str(provenance.get("runtime_root", ""))).resolve() != runtime_root:
            raise ValueError("runtime provenance root differs from selected userspace")
        critical_files = provenance.get("critical_files")
        if not isinstance(critical_files, list) or not critical_files:
            raise ValueError("runtime provenance has no critical file hashes")
        for item in critical_files:
            relative = Path(str(item.get("path", "")))
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"invalid critical runtime path: {relative}")
            path = runtime_root / relative
            if not path.is_file():
                raise ValueError(f"critical runtime file is missing: {relative}")
            actual_hash = sha256(path)
            if actual_hash != item.get("sha256"):
                raise ValueError(f"critical runtime hash mismatch: {relative}")
            verified_files.append(
                {"path": str(relative), "size_bytes": path.stat().st_size, "sha256": actual_hash}
            )

    return {
        "schema_version": 1,
        "status": "pass",
        "track": track,
        "runtime_root": str(runtime_root),
        "rocm_userspace_version": actual_version,
        "expected_build_version": expected_version,
        "expected_source_image_digest": expected["image_digest"],
        "source_image_digest": provenance.get("source_manifest_digest") if provenance else None,
        "provenance_manifest": str(provenance_path.resolve()) if provenance_path else None,
        "verified_critical_files": verified_files,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--track", required=True, choices=("reference", "candidate"))
    parser.add_argument("--matrix", default="config/build-matrix.json", type=Path)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.runtime_root, args.track, args.matrix, args.provenance)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        parser.exit(1, f"ROCm runtime verification failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
