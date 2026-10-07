#!/bin/bash
# 兼容入口：所有环境修复统一经过验证和历史审计。
set -euo pipefail
support="$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "${1:-}" = --frontend ]; then
    shift
    exec /bin/bash "$support/scripts/frontend-env.sh" "$@"
fi
exec /bin/bash "$support/scripts/repair-env.sh" "$@"
