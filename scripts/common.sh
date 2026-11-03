#!/usr/bin/env bash
# 他のスクリプトから source する。
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi
export HF_HOME="${HF_HOME:-$PROJECT_DIR/runtime/huggingface}"
export HF_HUB_DISABLE_TELEMETRY=1
export VLLM_CACHE_ROOT="${VLLM_CACHE_ROOT:-$PROJECT_DIR/runtime/vllm-cache}"
export TRITON_CACHE_DIR="${TRITON_CACHE_DIR:-$PROJECT_DIR/runtime/triton-cache}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PROJECT_DIR/runtime/uv-cache}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$PROJECT_DIR/runtime/xdg-cache}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$PROJECT_DIR/runtime/xdg-config}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-$PROJECT_DIR/runtime/xdg-data}"
export TORCH_HOME="${TORCH_HOME:-$PROJECT_DIR/runtime/torch}"
export TORCHINDUCTOR_CACHE_DIR="${TORCHINDUCTOR_CACHE_DIR:-$PROJECT_DIR/runtime/torchinductor-cache}"
export TORCH_EXTENSIONS_DIR="${TORCH_EXTENSIONS_DIR:-$PROJECT_DIR/runtime/torch-extensions}"
export CUDA_CACHE_PATH="${CUDA_CACHE_PATH:-$PROJECT_DIR/runtime/cuda-cache}"
export VLLM_CONFIG_ROOT="${VLLM_CONFIG_ROOT:-$PROJECT_DIR/runtime/vllm-config}"
export FLASHINFER_WORKSPACE_BASE="${FLASHINFER_WORKSPACE_BASE:-$PROJECT_DIR/runtime/flashinfer}"
export TMPDIR="$PROJECT_DIR/runtime/tmp"
mkdir -p "$TMPDIR" "$CUDA_CACHE_PATH" "$XDG_CACHE_HOME"
export PYTHONUNBUFFERED=1
export TOKENIZERS_PARALLELISM=false
ENV_DIR="${UV_PROJECT_ENVIRONMENT:-$PROJECT_DIR/.venv}"
PYTHON="$ENV_DIR/bin/python"

require_env() {
    if [[ ! -x "$PYTHON" ]]; then
        echo "先に $PROJECT_DIR/setup/install.sh を実行してください。" >&2
        exit 1
    fi
}

resolve_config() {
    CONFIG_FILE="${1:-configs/local.yaml}"
    if [[ "$CONFIG_FILE" != /* ]]; then
        if [[ -f "$CONFIG_FILE" ]]; then
            CONFIG_FILE="$(cd "$(dirname "$CONFIG_FILE")" && pwd)/$(basename "$CONFIG_FILE")"
        else
            CONFIG_FILE="$PROJECT_DIR/$CONFIG_FILE"
        fi
    fi
    if [[ ! -f "$CONFIG_FILE" ]]; then
        echo "設定がありません: $CONFIG_FILE" >&2
        echo "cp $PROJECT_DIR/configs/server.sample.yaml $PROJECT_DIR/configs/local.yaml" >&2
        exit 1
    fi
}
