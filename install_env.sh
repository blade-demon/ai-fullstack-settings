#!/usr/bin/env bash
# 保留原命令行入口；组员使用 dev-kit/开始配置.command。
set -euo pipefail
kit_root="$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/dev-kit/.support" && pwd)"
exec /bin/bash "$kit_root/install_env.sh" "$@"
