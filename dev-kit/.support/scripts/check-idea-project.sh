#!/bin/bash
set -euo pipefail
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/lib" && pwd)/common.sh"
source "$REPO_ROOT/scripts/lib/environment.sh"
source "$REPO_ROOT/scripts/lib/idea-project.sh"
parse_args "$@"
if "$SHOW_HELP"; then
    log '用法：check-idea-project.sh --project 项目路径 [--dry-run]'
    log '只读检查 Project SDK、Gradle JVM 和分发配置；静态通过仍需 IDEA 实际同步。'
    exit 0
fi
[ -n "$PROJECT_DIR" ] && [ -d "$PROJECT_DIR" ] || die '请通过 --project 指定实际项目目录'
if "$DRY_RUN"; then
    log "[预演] 检查 ${PROJECT_DIR} 的 IDEA 项目 SDK、Gradle JVM、分发配置及登记的 JDK 8。"
    log '[预演] 不运行 SDK、Gradle 或 IDEA，不修改配置。'
    exit 0
fi
probe_jdk8
probe_managed_configuration
probe_idea_project "$PROJECT_DIR"
report_idea_project
[ "$PROBE_IDEA_PROJECT_STATE" != ready ] || exit 0
# 2 表示需要在 IDEA 中配置/导入，不把终端构建的成功当作 IDE 已就绪。
exit 2
