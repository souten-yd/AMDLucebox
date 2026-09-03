#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
expected_arch=${EXPECTED_HIP_ARCH:-gfx1201}
hip_visible_devices=${HIP_VISIBLE_DEVICES:-0}
diagnostics_dir=${1:-r9700-diagnostics}
rocm_root=${ROCM_PATH:-/opt/rocm}

[[ $expected_arch == gfx1201 ]] || { echo "error: AMDLucebox preflight requires gfx1201" >&2; exit 1; }
[[ -e /dev/kfd ]] || { echo "error: /dev/kfd is missing" >&2; exit 1; }
[[ -d /dev/dri ]] || { echo "error: /dev/dri is missing" >&2; exit 1; }
[[ -x $rocm_root/bin/rocminfo ]] || { echo "error: rocminfo is missing under $rocm_root" >&2; exit 1; }
[[ -x $rocm_root/bin/hipcc ]] || { echo "error: hipcc is missing under $rocm_root" >&2; exit 1; }
mkdir -p "$diagnostics_dir"

export HIP_VISIBLE_DEVICES="$hip_visible_devices"
"$rocm_root/bin/rocminfo" > "$diagnostics_dir/rocminfo.txt" 2>&1 &
probe=$!
for _ in $(seq 1 15); do
  kill -0 "$probe" 2>/dev/null || break
  sleep 1
done
if kill -0 "$probe" 2>/dev/null; then
  echo "error: rocminfo hung; ROCm/KFD is likely wedged" >&2
  ps -o pid,stat,wchan:32,comm -p "$probe" | tee "$diagnostics_dir/rocminfo-process.txt" || true
  fuser -v /dev/kfd > "$diagnostics_dir/kfd-holders.txt" 2>&1 || true
  ps -eo pid,user,stat,wchan:32,comm > "$diagnostics_dir/processes.txt" || true
  dmesg 2>/dev/null | grep -iE 'amdgpu|kfd' | tail -100 > "$diagnostics_dir/amdgpu-dmesg.txt" || true
  kill -9 "$probe" 2>/dev/null || true
  disown "$probe" 2>/dev/null || true
  exit 1
fi
wait "$probe" || { tail -20 "$diagnostics_dir/rocminfo.txt" >&2; exit 1; }
grep -F "$expected_arch" "$diagnostics_dir/rocminfo.txt" >/dev/null || {
  echo "error: rocminfo does not report $expected_arch for HIP_VISIBLE_DEVICES=$HIP_VISIBLE_DEVICES" >&2
  exit 1
}

"$rocm_root/bin/hipcc" --offload-arch="$expected_arch" -O2 \
  "$repo_root/tests/hip_smoke.cpp" -o "$diagnostics_dir/hip_smoke"
"$diagnostics_dir/hip_smoke" "$expected_arch" | tee "$diagnostics_dir/hip-smoke.txt"
"$rocm_root/bin/hipcc" --version > "$diagnostics_dir/hipcc-version.txt" 2>&1
printf 'R9700 preflight passed for %s\n' "$expected_arch"
