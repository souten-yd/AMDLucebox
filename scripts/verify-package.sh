#!/usr/bin/env bash
set -euo pipefail

[[ $# -eq 1 ]] || { echo "Usage: verify-package.sh DIR|ARCHIVE.tar.zst" >&2; exit 2; }
input=$1
temporary=""
cleanup() { [[ -z $temporary ]] || rm -rf "$temporary"; }
trap cleanup EXIT

if [[ -d $input ]]; then
  root=$input
elif [[ -f $input && $input == *.tar.zst ]]; then
  temporary=$(mktemp -d)
  tar --zstd -xf "$input" -C "$temporary"
  root="$temporary/lucebox-r9700"
else
  echo "error: expected a package directory or .tar.zst archive" >&2
  exit 2
fi

required=(
  server/build/dflash_server README-R9700.md BUILD_INFO.json
  DEPENDENCIES.txt TOOLCHAIN.txt CMAKE_CACHE.txt OFFLOAD.txt SUBMODULES.txt
  LICENSES/LUCEBOX-LICENSE LICENSES/llama.cpp-LICENSE
)
for path in "${required[@]}"; do
  [[ -e $root/$path ]] || { echo "error: package is missing $path" >&2; exit 1; }
done
[[ -x $root/server/build/dflash_server ]] || { echo "error: dflash_server is not executable" >&2; exit 1; }
! grep -F 'not found' "$root/DEPENDENCIES.txt" >/dev/null || { echo "error: unresolved runtime dependency" >&2; exit 1; }
grep -Eq '^CMAKE_HIP_ARCHITECTURES(:[^=]+)?=gfx1201$' "$root/CMAKE_CACHE.txt" || {
  echo "error: CMake cache does not prove gfx1201" >&2; exit 1;
}
grep -F gfx1201 "$root/OFFLOAD.txt" >/dev/null || { echo "error: HIP code object does not prove gfx1201" >&2; exit 1; }

python3 - "$root/BUILD_INFO.json" <<'PY'
import json, re, sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
required = {
    "project", "build_track", "upstream_repository", "upstream_commit",
    "upstream_short_commit", "target_gpu", "gpu_architecture", "llvm_target",
    "os_target", "architecture", "rocm_version", "rocm_container",
    "rocm_container_digest", "cmake_build_type", "hip_compiler", "build_flags",
    "build_time_utc", "amdlucebox_commit"
}
missing = sorted(required - data.keys())
if missing:
    raise SystemExit(f"missing BUILD_INFO fields: {', '.join(missing)}")
if data["project"] != "AMDLucebox" or data["llvm_target"] != "gfx1201":
    raise SystemExit("invalid project or LLVM target")
if not re.fullmatch(r"[0-9a-f]{40}", data["upstream_commit"]):
    raise SystemExit("invalid upstream commit")
if not re.fullmatch(r"sha256:[0-9a-f]{64}", data["rocm_container_digest"]):
    raise SystemExit("invalid container digest")
if "DFLASH27B_HIP_ARCHITECTURES=gfx1201" not in data["build_flags"]:
    raise SystemExit("missing gfx1201 build flag")
PY

if find "$root" -type f \( -iname '*.gguf' -o -iname '*.safetensors' \) -print -quit | grep -q .; then
  echo "error: model weights must not be packaged" >&2
  exit 1
fi
