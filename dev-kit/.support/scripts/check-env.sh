#!/bin/bash
set -euo pipefail
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/lib" && pwd)/common.sh"
source "$REPO_ROOT/scripts/lib/environment.sh"
source "$REPO_ROOT/scripts/lib/managed-env.sh"
parse_args "$@"
if "$SHOW_HELP"; then
    log '用法：check-env.sh [--project 项目路径]；扫描JDK8、Gradle4.5.1、IDEA和完整环境配置，不执行构建。'
    exit 0
fi
"$DRY_RUN" && die '环境扫描本身只读，无需 --dry-run'
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
    log "[配置完整] GRADLE_4_5_1_HOME=$PROBE_CONFIG_GRADLE_ALIAS"
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
    else log '[缺失] 所选项目不存在或缺少 build.gradle/build.gradle.kts。'; failed=1; fi
else log '[未选择项目] 本次未执行构建，不能据此宣称业务项目通过。'; fi
log '[验证边界] 扫描不运行 Gradle 构建或启动 IDEA；签名、运行时、插件与项目构建由修复后的验证步骤确认。'
if [ "$failed" -ne 0 ]; then log '[一键修复] 检测到缺失配置，可选择菜单 1；每次修复均保存可 review 的历史。'
else log '[后续验证] 软件及配置静态检查齐全；可选择菜单 1 执行完整验证和项目构建。'; fi
exit "$failed"
