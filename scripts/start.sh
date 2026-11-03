#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_env
resolve_config "${1:-}"
if [[ $# -gt 0 ]]; then shift; fi
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
case "${LOG_VERBOSITY:-3}" in
    0|1|2) export VLLM_LOGGING_LEVEL=WARNING ;;
    3) export VLLM_LOGGING_LEVEL=INFO ;;
    4|5) export VLLM_LOGGING_LEVEL=DEBUG ;;
    *) echo "LOG_VERBOSITY は0〜5で指定してください。" >&2; exit 1 ;;
esac
echo "設定: $CONFIG_FILE"
echo "モデル保存先: $PROJECT_DIR/models"
echo "オフライン起動（未取得なら scripts/download.sh を実行してください）"
# vllm を新たに uv run しない。固定済み環境をそのまま実行する。
cd "$PROJECT_DIR"
exec "$PYTHON" "$PROJECT_DIR/scripts/launch.py" "$CONFIG_FILE" "$@"
