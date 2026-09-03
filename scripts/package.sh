#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build_root=""
source_root=""
output_dir=""
track=""
rocm_version=""
container=""
container_digest=""
upstream_sha=""
amdlucebox_sha=""
build_time=""

usage() {
  echo "Usage: package.sh --build-root DIR --source-root DIR --output-dir DIR --track NAME --rocm-version VERSION --container IMAGE --container-digest DIGEST --upstream-sha SHA --amdlucebox-sha SHA --build-time UTC" >&2
}

while (($#)); do
  case "$1" in
    --build-root) build_root=${2:?}; shift 2 ;;
    --source-root) source_root=${2:?}; shift 2 ;;
    --output-dir) output_dir=${2:?}; shift 2 ;;
    --track) track=${2:?}; shift 2 ;;
    --rocm-version) rocm_version=${2:?}; shift 2 ;;
    --container) container=${2:?}; shift 2 ;;
    --container-digest) container_digest=${2:?}; shift 2 ;;
    --upstream-sha) upstream_sha=${2:?}; shift 2 ;;
    --amdlucebox-sha) amdlucebox_sha=${2:?}; shift 2 ;;
    --build-time) build_time=${2:?}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

for value_name in build_root source_root output_dir track rocm_version container container_digest upstream_sha amdlucebox_sha build_time; do
  [[ -n ${!value_name} ]] || { echo "error: --${value_name//_/-} is required" >&2; exit 2; }
done
[[ $upstream_sha =~ ^[0-9a-f]{40}$ ]] || { echo "error: invalid upstream SHA" >&2; exit 1; }
[[ $amdlucebox_sha =~ ^[0-9a-f]{40}$ ]] || { echo "error: invalid AMDLucebox SHA" >&2; exit 1; }
[[ $container_digest =~ ^sha256:[0-9a-f]{64}$ ]] || { echo "error: invalid container digest" >&2; exit 1; }
[[ -x $build_root/server/build/dflash_server ]] || { echo "error: dflash_server is missing" >&2; exit 1; }

short_sha=${upstream_sha:0:8}
package_name="lucebox-r9700-rocm${rocm_version}-gfx1201-${short_sha}"
mkdir -p "$output_dir"
stage_parent=$(mktemp -d)
cleanup() { rm -rf "$stage_parent"; }
trap cleanup EXIT
stage="$stage_parent/lucebox-r9700"
mkdir -p "$stage"
cp -a "$build_root/server" "$stage/server"
cp -a "$build_root/LICENSES" "$stage/LICENSES"
cp "$build_root/verification/DEPENDENCIES.txt" "$stage/DEPENDENCIES.txt"
cp "$build_root/verification/TOOLCHAIN.txt" "$stage/TOOLCHAIN.txt"
cp "$build_root/verification/CMAKE_CACHE.txt" "$stage/CMAKE_CACHE.txt"
cp "$build_root/verification/OFFLOAD.txt" "$stage/OFFLOAD.txt"
cp "$repo_root/docs/README-R9700.md" "$stage/README-R9700.md"
git -C "$source_root" submodule status --recursive > "$stage/SUBMODULES.txt"

python3 - "$stage/BUILD_INFO.json" <<PY
import json
from pathlib import Path

data = {
    "project": "AMDLucebox",
    "build_track": ${track@Q},
    "upstream_repository": "Luce-Org/lucebox",
    "upstream_commit": ${upstream_sha@Q},
    "upstream_short_commit": ${short_sha@Q},
    "target_gpu": "AMD Radeon AI PRO R9700",
    "gpu_architecture": "RDNA4",
    "llvm_target": "gfx1201",
    "os_target": "Ubuntu 24.04",
    "architecture": "x86_64",
    "rocm_version": ${rocm_version@Q},
    "rocm_container": ${container@Q},
    "rocm_container_digest": ${container_digest@Q},
    "cmake_build_type": "Release",
    "hip_compiler": "/opt/rocm/lib/llvm/bin/clang++",
    "build_flags": [
        "DFLASH27B_GPU_BACKEND=hip",
        "DFLASH27B_HIP_ARCHITECTURES=gfx1201",
        "DFLASH27B_FA_ALL_QUANTS=OFF",
        "DFLASH27B_ENABLE_BSA=OFF",
        "GGML_HIP_MMQ_MFMA=ON",
        "GGML_HIP_NO_VMM=ON"
    ],
    "build_time_utc": ${build_time@Q},
    "amdlucebox_commit": ${amdlucebox_sha@Q}
}
Path(${stage@Q} + "/BUILD_INFO.json").write_text(
    json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

"$repo_root/scripts/verify-package.sh" "$stage"
archive="$output_dir/$package_name.tar.zst"
tar --sort=name --mtime="$build_time" --owner=0 --group=0 --numeric-owner \
  --zstd -cf "$archive" -C "$stage_parent" lucebox-r9700
"$repo_root/scripts/verify-package.sh" "$archive"
(cd "$output_dir" && sha256sum "$(basename "$archive")") > "$archive.sha256"
printf '%s\n' "$archive"
