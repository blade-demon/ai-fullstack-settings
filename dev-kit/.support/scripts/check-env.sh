#!/bin/bash
set -euo pipefail
scan_gradle_explicit="${GRADLE_VERSION:-}"
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/lib" && pwd)/common.sh"
source "$REPO_ROOT/scripts/lib/environment.sh"
source "$REPO_ROOT/scripts/lib/managed-env.sh"
source "$REPO_ROOT/scripts/lib/idea-project.sh"
parse_args "$@"
if "$SHOW_HELP"; then
    log '用法：check-env.sh [--project 项目路径]；扫描 JDK 8、当前 Gradle（4.5.1 / 6.8）、IDEA 和完整环境配置，不执行构建。'
    exit 0
fi
"$DRY_RUN" && die '环境扫描本身只读，无需 --dry-run'
# 未指定目标版本时，菜单启动扫描跟随已配置的 Gradle，避免将 6.8 误报为缺失。
if [ -z "$scan_gradle_explicit" ]; then
    scan_gradle_home="$(managed_env_saved_value GRADLE_HOME)" || scan_gradle_home=''
    scan_gradle_version="$(_probe_distribution_version "$scan_gradle_home")" || scan_gradle_version=''
    case "$scan_gradle_version" in 4.5.1|6.8) GRADLE_VERSION="$scan_gradle_version" ;; esac
fi
probe_jdk8; probe_managed_configuration; probe_idea
failed=0
log '当前系统环境配置：'
if [ -n "$PROBE_JDK_HOME" ]; then
    log "[已安装] JDK 8（${PROBE_JDK_VERSION}）：$PROBE_JDK_HOME"
else log '[缺失] 未找到可用的 JDK 8（java/javac 均需1.8）。'; failed=1; fi
if [ "$PROBE_JDK_CONFIG" = ready ]; then
    log "[配置完整] JAVA_HOME=$PROBE_CONFIG_JAVA_HOME"
    log "[配置完整] JAVA_8_HOME=$PROBE_CONFIG_JAVA_8_HOME"
    log "[配置完整] JRE_HOME=${PROBE_CONFIG_JRE_HOME}；java PATH 已指向此 JDK。"
else log '[待修复] JAVA_HOME、JAVA_8_HOME、JRE_HOME 或 Java PATH 不完整。'; failed=1; fi
if [ "$PROBE_GRADLE_CONFIG" = ready ]; then
    log "[已安装] 独立 Gradle ${GRADLE_VERSION}：$PROBE_CONFIG_GRADLE_HOME"
    log "[配置完整] GRADLE_HOME=$PROBE_CONFIG_GRADLE_HOME"
    log "[配置完整] $(gradle_alias_name)=$PROBE_CONFIG_GRADLE_ALIAS"
    log "[配置完整] GRADLE_USER_HOME=${PROBE_CONFIG_GRADLE_USER_HOME}；gradle PATH 已指向目标版本。"
else
    log "[待修复] 独立 Gradle ${GRADLE_VERSION} 或 GRADLE_HOME、版本别名、用户缓存目录、PATH 不完整。"
    failed=1
fi
if [ "$PROBE_PROFILE_CONFIG" = ready ]; then log '[配置完整] Shell 已配置受管环境加载入口。'
else log '[待修复] Shell 配置未加载受管环境，新终端可能无法使用。'; failed=1; fi
case "$PROBE_IDEA_STATE" in
    installed) log "[已安装] IDEA ${PROBE_IDEA_VERSION}（${PROBE_IDEA_BUILD}）：$PROBE_IDEA_PATH" ;;
    missing) log "[缺失] IDEA：$PROBE_IDEA_PATH"; failed=1 ;;
    *) log "[待处理] IDEA 版本或应用结构不符合基线，保留现有应用：$PROBE_IDEA_PATH"; failed=1 ;;
esac
probe_gradle "$PROJECT_DIR"
if [ -n "$PROBE_GRADLE_GLOBAL_COMMAND" ]; then
    log "[当前命令参考] ${PROBE_GRADLE_GLOBAL_COMMAND}（静态版本：${PROBE_GRADLE_GLOBAL_VERSION:-待验证}）"
fi
if [ "$PROBE_GRADLE_STATE" = project_cached ]; then log "[Wrapper缓存] ${PROBE_GRADLE_PATH}（仅供参考，默认构建使用已验证的独立 Gradle）"; fi
if [ -n "$PROJECT_DIR" ]; then
    if [ -d "$PROJECT_DIR" ] && { [ -f "$PROJECT_DIR/build.gradle" ] || [ -f "$PROJECT_DIR/build.gradle.kts" ]; }; then
        log "[待构建验证] ${PROJECT_DIR}；必须实际 build 成功才确认最终任务成功。"
        probe_idea_project "$PROJECT_DIR"
        report_idea_project
        [ "$PROBE_IDEA_PROJECT_STATE" = ready ] || failed=1
    else log '[缺失] 所选项目不存在或缺少 build.gradle/build.gradle.kts。'; failed=1; fi
else log '[未选择项目] 本次未执行构建，不能据此宣称业务项目通过。'; fi
log '[验证边界] 扫描不运行 Gradle 构建或启动 IDEA；签名、运行时、插件与项目构建由修复后的验证步骤确认。'
if [ "$failed" -ne 0 ]; then log '[后续配置] 检测到缺失配置，请进入“安装与配置”选择需要的组件。'
else log '[后续验证] 软件及配置静态检查齐全，可通过“安装与配置”验证所选组件；业务项目请按项目文档另行验证。'; fi
exit "$failed"
