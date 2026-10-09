#!/usr/bin/env bash
# 退出 IDEA 后，将一个已导入项目的 SDK 名称与实际 JDK 8 目录同步。
set -euo pipefail
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/common.sh"
source "$REPO_ROOT/scripts/lib/environment.sh"
source "$REPO_ROOT/scripts/lib/idea-project.sh"
source "$REPO_ROOT/scripts/lib/idea-sdk.sh"
global_only=false
if [ "${1:-}" = --global ]; then global_only=true; shift; fi
parse_args "$@"
if "$SHOW_HELP"; then
    log '用法：bash scripts/runtime/config-idea-sdk.sh --project 项目目录 [--dry-run]'
    log 'IDEA 必须退出；IDEA_JDK_NAME 默认 azul-1.8，可通过 config/env.sh 或环境变量设置。'
    exit 0
fi
if "$global_only"; then
    [ -z "$PROJECT_DIR" ] || die '--global 不接受项目参数'
    idea_sdk_register_global
    exit $?
fi
[ -n "$PROJECT_DIR" ] || die '请通过 --project 指定已在 IDEA 中导入的项目'
IDEA_JDK_NAME="${IDEA_JDK_NAME:-azul-1.8}"
idea_sdk_sync "$PROJECT_DIR"
