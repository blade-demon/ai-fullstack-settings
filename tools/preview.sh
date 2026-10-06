#!/bin/bash
# macOS/Linux 兼容入口；Windows 直接使用 server/manage.py。
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
command -v python3 >/dev/null 2>&1 || { printf '需要 Python 3.8 或更新版本。\n' >&2; exit 1; }
exec python3 "$ROOT/server/manage.py" preview "$@"
