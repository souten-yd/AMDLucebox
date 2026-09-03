#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
binary=""
model=""
draft=""
output="benchmark-r9700.json"
port=8216
reference_results=""
warmups=3
max_tokens=256
metrics_output=""

while (($#)); do
  case "$1" in
    --binary) binary=${2:?}; shift 2 ;;
    --model) model=${2:?}; shift 2 ;;
    --draft) draft=${2:?}; shift 2 ;;
    --output) output=${2:?}; shift 2 ;;
    --port) port=${2:?}; shift 2 ;;
    --reference-results) reference_results=${2:?}; shift 2 ;;
    --warmups) warmups=${2:?}; shift 2 ;;
    --max-tokens) max_tokens=${2:?}; shift 2 ;;
    --metrics-output) metrics_output=${2:?}; shift 2 ;;
    *) echo "error: unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -x $binary ]] || { echo "error: --binary is not executable" >&2; exit 1; }
[[ -f $model ]] || { echo "error: --model is missing" >&2; exit 1; }
[[ -f $draft ]] || { echo "error: --draft is missing" >&2; exit 1; }
[[ $port =~ ^[0-9]+$ ]] || { echo "error: --port must be numeric" >&2; exit 2; }
[[ $warmups =~ ^[0-9]+$ ]] || { echo "error: --warmups must be a non-negative integer" >&2; exit 2; }
[[ $max_tokens =~ ^[1-9][0-9]*$ ]] || { echo "error: --max-tokens must be a positive integer" >&2; exit 2; }

log_file=${output%.json}.server.log
metrics_pid=""
if [[ -n $metrics_output ]]; then
  python3 "$repo_root/scripts/sample-r9700-metrics.py" --output "$metrics_output" --interval 2 &
  metrics_pid=$!
fi
"$binary" "$model" --draft "$draft" --draft-block-size 16 --max-ctx 131072 \
  --cache-type-k q8_0 --cache-type-v q8_0 --port "$port" > "$log_file" 2>&1 &
server_pid=$!
cleanup() {
  if [[ -n $metrics_pid ]]; then
    kill "$metrics_pid" 2>/dev/null || true
    wait "$metrics_pid" 2>/dev/null || true
  fi
  kill "$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
}
trap cleanup EXIT

ready=false
for _ in $(seq 1 180); do
  kill -0 "$server_pid" 2>/dev/null || { tail -100 "$log_file" >&2; exit 1; }
  if curl -fsS --max-time 2 "http://127.0.0.1:$port/v1/models" >/dev/null; then ready=true; break; fi
  sleep 2
done
$ready || { echo "error: server did not become ready" >&2; tail -100 "$log_file" >&2; exit 1; }

benchmark_args=(
  --base-url "http://127.0.0.1:$port" --output "$output"
  --warmups "$warmups" --max-tokens "$max_tokens"
)
[[ -z $reference_results ]] || benchmark_args+=(--reference-results "$reference_results")
python3 "$repo_root/scripts/benchmark-r9700.py" "${benchmark_args[@]}"
if [[ -n $metrics_pid ]]; then
  kill "$metrics_pid" 2>/dev/null || true
  wait "$metrics_pid"
  metrics_pid=""
fi
