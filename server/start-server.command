#!/bin/bash
set -euo pipefail
PAUSE_ON_FAILURE=0
if [ "$#" -eq 0 ] && [ -t 0 ] && [ -t 1 ]; then PAUSE_ON_FAILURE=1; fi
finish() {
  status=$?
  trap - EXIT
  if [ "$status" -ne 0 ] && [ "$PAUSE_ON_FAILURE" -eq 1 ]; then
    printf '\n启动未完成，请查看上面的提示。按回车关闭窗口…'
    IFS= read -r _ || true
  fi
  exit "$status"
}
trap finish EXIT
DIRECTORY="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
command -v python3 >/dev/null 2>&1 || { printf '需要 Python 3.8 或更新版本，请先阅读 docs/service-startup.md 的安装指引。\n' >&2; exit 1; }
python3 "$DIRECTORY/manage.py" "$@"
