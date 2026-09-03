#!/usr/bin/env bash
set -euo pipefail

repository="https://github.com/Luce-Org/lucebox.git"
ref="main"
github_output=""

usage() {
  cat <<'EOF'
Usage: resolve-upstream.sh [--repository URL] [--ref REF] [--github-output FILE]

Resolve a branch, tag, or full commit to an immutable Lucebox commit SHA.
Prints the full SHA to stdout. When --github-output is supplied, also writes
upstream_sha and upstream_short_sha entries for GitHub Actions.
EOF
}

while (($#)); do
  case "$1" in
    --repository) repository=${2:?missing repository}; shift 2 ;;
    --ref) ref=${2:?missing ref}; shift 2 ;;
    --github-output) github_output=${2:?missing output path}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ $ref =~ ^[0-9a-fA-F]{40}$ ]]; then
  sha=$(git ls-remote "$repository" | awk -v wanted="${ref,,}" \
    'tolower($1) == wanted { print tolower($1); exit }')
else
  sha=$(git ls-remote "$repository" "$ref" "refs/heads/$ref" "refs/tags/$ref" "refs/tags/$ref^{}" |
    awk '
      $2 ~ /\^\{\}$/ { peeled=$1 }
      $2 == "refs/heads/" ref || $2 == ref { direct=$1 }
      $2 == "refs/tags/" ref { tag=$1 }
      END {
        if (peeled) print peeled;
        else if (direct) print direct;
        else if (tag) print tag;
      }' ref="$ref")
fi

if [[ ! ${sha:-} =~ ^[0-9a-f]{40}$ ]]; then
  echo "error: unable to resolve upstream ref '$ref' from '$repository'" >&2
  exit 1
fi

short_sha=${sha:0:8}
printf '%s\n' "$sha"
if [[ -n $github_output ]]; then
  {
    printf 'upstream_sha=%s\n' "$sha"
    printf 'upstream_short_sha=%s\n' "$short_sha"
  } >> "$github_output"
fi
