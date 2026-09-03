#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
upstream_repository="https://github.com/Luce-Org/lucebox.git"
upstream_ref="main"
track=""
output_dir="$repo_root/dist"
keep_source=false

usage() {
  cat <<'EOF'
Usage: build.sh --track reference|candidate [options]

Options:
  --upstream-ref REF       Branch, tag, or full commit (default: main)
  --upstream-repository U  Lucebox git URL
  --output-dir DIR         Artifact output directory (default: ./dist)
  --keep-source            Retain the pinned source checkout beside output
EOF
}

while (($#)); do
  case "$1" in
    --track) track=${2:?missing track}; shift 2 ;;
    --upstream-ref) upstream_ref=${2:?missing ref}; shift 2 ;;
    --upstream-repository) upstream_repository=${2:?missing repository}; shift 2 ;;
    --output-dir) output_dir=${2:?missing output directory}; shift 2 ;;
    --keep-source) keep_source=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n $track ]] || { echo "error: --track is required" >&2; exit 2; }
command -v docker >/dev/null || { echo "error: docker with buildx is required" >&2; exit 1; }
docker buildx version >/dev/null

readarray -t track_values < <(python3 - "$repo_root/config/build-matrix.json" "$track" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
matches = [item for item in data["tracks"] if item["name"] == sys.argv[2]]
if len(matches) != 1:
    raise SystemExit(f"unknown build track: {sys.argv[2]}")
item = matches[0]
for key in ("rocm_version", "image_tag", "image_digest", "llvm_target"):
    print(item[key])
PY
)
rocm_version=${track_values[0]}
image_tag=${track_values[1]}
image_digest=${track_values[2]}
llvm_target=${track_values[3]}
[[ $llvm_target == gfx1201 ]] || { echo "error: refusing non-gfx1201 target" >&2; exit 1; }
[[ $image_digest =~ ^sha256:[0-9a-f]{64}$ ]] || { echo "error: image digest is not immutable" >&2; exit 1; }

upstream_sha=$("$repo_root/scripts/resolve-upstream.sh" \
  --repository "$upstream_repository" --ref "$upstream_ref")
upstream_short_sha=${upstream_sha:0:8}
work_dir=$(mktemp -d)
cleanup() { rm -rf "$work_dir"; }
trap cleanup EXIT

git -C "$work_dir" init --quiet source
git -C "$work_dir/source" remote add origin "$upstream_repository"
git -C "$work_dir/source" fetch --quiet --depth=1 origin "$upstream_sha"
git -C "$work_dir/source" checkout --quiet --detach FETCH_HEAD
actual_sha=$(git -C "$work_dir/source" rev-parse HEAD)
[[ $actual_sha == "$upstream_sha" ]] || { echo "error: checkout SHA mismatch" >&2; exit 1; }
git -C "$work_dir/source" submodule update --init --recursive --depth=1

export_dir="$work_dir/export"
mkdir -p "$export_dir"
docker buildx build \
  --file "$repo_root/docker/Dockerfile.build" \
  --target artifact \
  --build-arg "BASE_IMAGE=$image_tag@$image_digest" \
  --build-arg "LLVM_TARGET=$llvm_target" \
  --output "type=local,dest=$export_dir" \
  "$work_dir/source"

amdlucebox_commit=$(git -C "$repo_root" rev-parse HEAD)
build_time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
package_dir="$output_dir/$track"
mkdir -p "$package_dir"
"$repo_root/scripts/package.sh" \
  --build-root "$export_dir" \
  --source-root "$work_dir/source" \
  --output-dir "$package_dir" \
  --track "$track" \
  --rocm-version "$rocm_version" \
  --container "$image_tag" \
  --container-digest "$image_digest" \
  --upstream-sha "$upstream_sha" \
  --amdlucebox-sha "$amdlucebox_commit" \
  --build-time "$build_time_utc"

if $keep_source; then
  retained="$output_dir/upstream-$upstream_short_sha"
  [[ ! -e $retained ]] || { echo "error: retained source path already exists: $retained" >&2; exit 1; }
  mv "$work_dir/source" "$retained"
fi
