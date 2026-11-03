#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_env
exec "$PYTHON" "$PROJECT_DIR/scripts/download.py" "$@"
