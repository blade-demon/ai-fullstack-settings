#!/bin/bash
# 维护者实体机器重装测试；默认预览，删除必须显式 --apply。
set -euo pipefail
tool_root="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
command -v python3 >/dev/null 2>&1 || { printf '需要 Python 3.8 或更新版本，请按服务启动指南安装。\n' >&2; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' || { printf '需要 Python 3.8 或更新版本。\n' >&2; exit 1; }
exec python3 "$tool_root/uninstall_java_gradle.py" "$@"
