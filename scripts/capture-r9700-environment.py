#!/usr/bin/env python3
"""Capture a machine-readable R9700 runtime snapshot for acceptance evidence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def redact_hardware_identifiers(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "REDACTED" if any(token in key.lower() for token in ("serial", "uuid", "unique_id"))
            else redact_hardware_identifiers(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_hardware_identifiers(item) for item in value]
    return value


def command_result(command: list[str], parse_json: bool = False) -> dict[str, Any]:
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"command": command, "returncode": None, "error": str(error)}
    result: dict[str, Any] = {
        "command": command,
        "returncode": completed.returncode,
        "stderr": completed.stderr,
    }
    if parse_json and completed.returncode == 0:
        try:
            result["json"] = redact_hardware_identifiers(json.loads(completed.stdout))
        except json.JSONDecodeError:
            result["stdout"] = completed.stdout
            result["json_error"] = "invalid JSON output"
    else:
        result["stdout"] = completed.stdout
    return result


def capture(snapshot: str, hip_visible_devices: str) -> dict[str, Any]:
    commands = {
        "uname": command_result(["uname", "-a"]),
        "hipcc_version": command_result(["/opt/rocm/bin/hipcc", "--version"]),
        "amd_smi_version": command_result(["amd-smi", "version"]),
        "amd_smi_list": command_result(["amd-smi", "list", "--json"], parse_json=True),
        "amd_smi_static": command_result(["amd-smi", "static", "--json"], parse_json=True),
        "amd_smi_metric": command_result(["amd-smi", "metric", "--json"], parse_json=True),
        "amd_smi_process": command_result(["amd-smi", "process", "--json"], parse_json=True),
        "rocm_smi": command_result(
            [
                "rocm-smi",
                "--showproductname",
                "--showpower",
                "--showclocks",
                "--showtemp",
                "--showmeminfo",
                "vram",
                "--showuse",
                "--json",
            ],
            parse_json=True,
        ),
        "amdgpu_module": command_result(["modinfo", "amdgpu"]),
        "uptime": command_result(["uptime"]),
        "major_process_load": command_result(
            ["ps", "-eo", "pid,user,pcpu,pmem,comm", "--sort=-pcpu"]
        ),
    }
    os_release = Path("/etc/os-release").read_text(encoding="utf-8")
    rocm_version_path = Path("/opt/rocm/.info/version")
    required = (
        "uname",
        "hipcc_version",
        "amd_smi_version",
        "amd_smi_list",
        "amd_smi_static",
        "amd_smi_metric",
        "amd_smi_process",
        "rocm_smi",
        "amdgpu_module",
        "uptime",
        "major_process_load",
    )
    failed = [name for name in required if commands[name].get("returncode") != 0]
    return {
        "schema_version": 1,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot": snapshot,
        "hip_visible_devices": hip_visible_devices,
        "runner_name": os.environ.get("RUNNER_NAME"),
        "runner_os": os.environ.get("RUNNER_OS"),
        "runner_arch": os.environ.get("RUNNER_ARCH"),
        "os_release": os_release,
        "rocm_userspace_version": rocm_version_path.read_text(encoding="utf-8").strip(),
        "commands": commands,
        "failed_required_commands": failed,
        "status": "pass" if not failed else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", choices=("before", "after"), required=True)
    parser.add_argument("--hip-visible-devices", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = capture(args.snapshot, args.hip_visible_devices)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as error:
        parser.exit(1, f"environment capture failed: {error}\n")
    if result["status"] != "pass":
        parser.exit(1, "environment capture failed one or more required commands\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
