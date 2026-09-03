#!/usr/bin/env bash
set -euo pipefail

lucebox_source=""
model_dir=""
download_command=${HF_COMMAND:-hf}

usage() {
  cat <<'EOF'
Usage: prepare-qwen38.sh --lucebox-source DIR --model-dir DIR

Downloads the public Qwen3.8 target and DFlash2 source from Hugging Face, then
uses the pinned Lucebox checkout's conversion scripts to create the Q8_0 draft.
Model files remain outside Git and release artifacts.
EOF
}

while (($#)); do
  case "$1" in
    --lucebox-source) lucebox_source=${2:?}; shift 2 ;;
    --model-dir) model_dir=${2:?}; shift 2 ;;
    --hf-command) download_command=${2:?}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done
[[ -d $lucebox_source/.git ]] || { echo "error: --lucebox-source must be a pinned git checkout" >&2; exit 1; }
[[ -f $lucebox_source/server/scripts/convert_dflash_to_gguf.py ]] || { echo "error: current Lucebox converter is missing" >&2; exit 1; }
[[ -f $lucebox_source/server/scripts/quantize_dflash_draft.py ]] || { echo "error: current Lucebox quantizer is missing" >&2; exit 1; }
command -v "$download_command" >/dev/null || { echo "error: Hugging Face CLI '$download_command' is missing" >&2; exit 1; }
mkdir -p "$model_dir/dflash2"

"$download_command" download unsloth/Qwen3.8-27B-GGUF \
  Qwen3.8-27B-UD-IQ4_XS.gguf --local-dir "$model_dir"
"$download_command" download incoai/Qwen3.8-27B-DFlash2 \
  --local-dir "$model_dir/dflash2"
python3 "$lucebox_source/server/scripts/convert_dflash_to_gguf.py" \
  "$model_dir/dflash2/model.safetensors" "$model_dir/qwen38-dflash2-f16.gguf"
python3 "$lucebox_source/server/scripts/quantize_dflash_draft.py" \
  "$model_dir/qwen38-dflash2-f16.gguf" "$model_dir/qwen38-dflash2-q8_0.gguf" --scheme q8_0
printf 'Prepared target and Q8_0 DFlash2 draft in %s\n' "$model_dir"
