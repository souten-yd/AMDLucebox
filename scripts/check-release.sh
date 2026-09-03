#!/usr/bin/env bash
set -euo pipefail

repository=""
tag=""
force=false
github_output=""

while (($#)); do
  case "$1" in
    --repository) repository=${2:?}; shift 2 ;;
    --tag) tag=${2:?}; shift 2 ;;
    --force) force=${2:?}; shift 2 ;;
    --github-output) github_output=${2:?}; shift 2 ;;
    *) echo "error: unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -n $repository && -n $tag ]] || { echo "error: --repository and --tag are required" >&2; exit 2; }
[[ $force == true || $force == false ]] || { echo "error: --force must be true or false" >&2; exit 2; }
command -v gh >/dev/null || { echo "error: gh is required" >&2; exit 1; }

release_exists=false
if gh release view "$tag" --repo "$repository" >/dev/null 2>&1; then
  release_exists=true
fi
should_build=true
if [[ $release_exists == true && $force == false ]]; then
  should_build=false
fi
printf 'release_exists=%s\nshould_build=%s\n' "$release_exists" "$should_build"
if [[ -n $github_output ]]; then
  printf 'release_exists=%s\nshould_build=%s\n' "$release_exists" "$should_build" >> "$github_output"
fi
