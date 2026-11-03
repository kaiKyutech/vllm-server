#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../scripts/common.sh"
if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
    echo "対象は Linux / WSL2 の x86_64 + NVIDIA GPU です。" >&2; exit 1
fi
UV_BIN="$(command -v uv || true)"
if [[ -z "$UV_BIN" && -x "$PROJECT_DIR/.tools/uv" ]]; then
    UV_BIN="$PROJECT_DIR/.tools/uv"
fi
if [[ -z "$UV_BIN" ]]; then
    command -v curl >/dev/null || { echo "curl が必要です。" >&2; exit 1; }
    installer="$(mktemp)"
    trap 'rm -f "$installer"' EXIT
    curl -fsSL --retry 3 https://astral.sh/uv/0.10.7/install.sh -o "$installer"
    UV_UNMANAGED_INSTALL="$PROJECT_DIR/.tools" sh "$installer"
    UV_BIN="$PROJECT_DIR/.tools/uv"
fi
export UV_PROJECT_ENVIRONMENT="$ENV_DIR"
export UV_PYTHON_DOWNLOADS=never
cd "$PROJECT_DIR"
if [[ ! -f uv.lock ]]; then
    "$UV_BIN" lock --python "${PYTHON_BIN:-python3.12}"
fi
# ダウンロード済みwheelの恒久キャッシュを作らず、容量の二重使用を避ける。
"$UV_BIN" sync --frozen --no-cache --link-mode=copy --python "${PYTHON_BIN:-python3.12}"
if [[ ! -f configs/local.yaml ]]; then
    cp configs/server.sample.yaml configs/local.yaml
fi
echo "環境構築完了。このスクリプトではモデルの取得は行いません。"
echo "確認: ./scripts/doctor.sh"
echo "取得: ./scripts/download.sh Qwen/Qwen3.5-9B"
