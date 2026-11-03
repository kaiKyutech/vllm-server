#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
PORT="${1:-8000}"
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
    echo "ポートは1〜65535で指定してください。" >&2; exit 1
fi
CLOUDFLARED="${CLOUDFLARED:-$(command -v cloudflared || true)}"
if [[ -z "$CLOUDFLARED" && -x "$PROJECT_DIR/.tools/cloudflared" ]]; then
    CLOUDFLARED="$PROJECT_DIR/.tools/cloudflared"
fi
if [[ -z "$CLOUDFLARED" && -x "$HOME/bin/cloudflared" ]]; then
    CLOUDFLARED="$HOME/bin/cloudflared"
fi
if [[ -z "$CLOUDFLARED" ]]; then
    echo "cloudflared がありません。README のインストール手順を参照してください。" >&2
    exit 1
fi
if ! curl -fsS --max-time 3 "http://127.0.0.1:$PORT/health" >/dev/null; then
    echo "vLLM が応答しません。先に start.sh で起動してください。" >&2; exit 1
fi
echo "公開先: http://127.0.0.1:$PORT（終了: Ctrl+C）"
exec "$CLOUDFLARED" tunnel --protocol "${TUNNEL_PROTOCOL:-http2}" \
    --url "http://127.0.0.1:$PORT" --no-autoupdate
