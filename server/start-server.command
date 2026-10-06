#!/bin/bash
set -euo pipefail
DIRECTORY="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
command -v python3 >/dev/null 2>&1 || { printf '需要 Python 3.8 或更新版本。\n' >&2; exit 1; }
exec python3 "$DIRECTORY/manage.py" "$@"
