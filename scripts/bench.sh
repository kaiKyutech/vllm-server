#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_env
cd "$PROJECT_DIR"
exec "$PYTHON" "$PROJECT_DIR/scripts/bench.py" "$@"
