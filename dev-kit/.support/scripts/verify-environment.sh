#!/bin/bash
set -euo pipefail
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/lib" && pwd)/common.sh"
source "$REPO_ROOT/scripts/lib/environment.sh"
source "$REPO_ROOT/scripts/lib/managed-env.sh"
scope=all
while [ "$#" -gt 0 ]; do
    case "$1" in
        --scope) [ "$#" -ge 2 ] || die '--scope 后需要范围'; scope="$2"; shift 2 ;;
        --help|-h) log '用法：verify-environment.sh [--scope all|jdk|gradle|idea|plugins]'; exit 0 ;;
        *) die "未知参数：$1" ;;
    esac
done
case "$scope" in all|jdk|gradle|idea|plugins) ;; *) die '不支持的验证范围' ;; esac
case "$scope" in
    all|jdk|gradle)
        probe_jdk8; probe_managed_configuration
        [ "$PROBE_JDK_CONFIG" = ready ] && [ "$PROBE_PROFILE_CONFIG" = ready ] || die 'JDK 完整环境变量或Shell加载入口验证失败'
        verify_profile_configuration "$scope" || die '终端配置加载验证失败（Shell配置提前返回、覆盖变量或执行超过5秒）；未确认完整环境。此检查使用非交互子进程，不等同于完整交互终端。'
        log "[验证通过] JDK ${PROBE_JDK_VERSION}、JAVA_HOME、JAVA_8_HOME、JRE_HOME 和 PATH。"
        ;;
esac
case "$scope" in
    all|gradle)
        [ "$PROBE_GRADLE_CONFIG" = ready ] || die 'Gradle 分发、完整环境变量或 PATH 验证失败'
        version_output="$(/usr/bin/env -i HOME="$HOME" PATH='/usr/bin:/bin:/usr/sbin:/sbin' /bin/bash -c '
            source "$1" || exit 1
            "$GRADLE_HOME/bin/gradle" --version
        ' verify "$ENV_FILE" 2>&1)" || { printf '%s\n' "$version_output"; die 'Gradle 无法实际运行'; }
        actual="$(printf '%s\n' "$version_output" | awk '/^Gradle[ \t]+/ {sub(/\r$/, ""); if (NF==2) print $2}')"
        [ "$actual" = "$GRADLE_VERSION" ] || die "Gradle 实际版本错误：${actual:-未知}"
        log "[验证通过] Gradle ${actual}、GRADLE_HOME、$(gradle_alias_name)、GRADLE_USER_HOME 和 PATH。"
        ;;
esac
case "$scope" in
    all|idea)
        probe_idea
        [ "$PROBE_IDEA_STATE" = installed ] || die 'IDEA 版本或应用结构验证失败'
        require_command codesign
        codesign --verify --deep --strict "$PROBE_IDEA_PATH" || die 'IDEA 代码签名验证失败'
        jbr="$PROBE_IDEA_PATH/Contents/jbr/Contents/Home/bin/java"
        [ -x "$jbr" ] || die 'IDEA 自带运行时缺失'
        "$jbr" -version || die 'IDEA 自带运行时无法执行'
        log "[验证通过] IDEA ${PROBE_IDEA_VERSION} 的应用结构、签名和自带运行时；未启动GUI。"
        ;;
esac
case "$scope" in
    all|plugins) /bin/bash "$REPO_ROOT/scripts/software/install-idea-plugins.sh" --verify-only ;;
esac
log '本阶段验证通过；是否完成项目构建以独立构建步骤结果为准。'
