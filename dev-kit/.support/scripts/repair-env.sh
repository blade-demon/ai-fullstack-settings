#!/bin/bash
set -euo pipefail
umask 077
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/lib" && pwd)/common.sh"
source "$REPO_ROOT/scripts/lib/audit.sh"
scope=all; project=''; dry_run=false
while [ "$#" -gt 0 ]; do
    case "$1" in
        --scope|--project)
            [ "$#" -ge 2 ] && [ -n "$2" ] || die "$1 后需要值"
            case "$2" in --*) die "$1 后需要值" ;; esac
            if [ "$1" = --scope ]; then scope="$2"; else project="$2"; fi
            shift 2 ;;
        --dry-run) dry_run=true; shift ;;
        --help|-h)
            log '用法：repair-env.sh [--scope all|jdk|gradle|idea|plugins] [--project 项目] [--dry-run]'
            log '扫描、修复、验证并保存历史；指定项目后必须通过 Gradle build 才报告成功。'
            exit 0 ;;
        *) die "未知参数：$1" ;;
    esac
done
case "$scope" in all|jdk|gradle|idea|plugins) ;; *) die "未知修复范围：$scope" ;; esac
validate_server
if [ -n "$project" ]; then
    [ -d "$project" ] || die "项目目录不存在：$project"
    project="$(CDPATH= cd -- "$project" && pwd -P)"
    [ -f "$project/build.gradle" ] || [ -f "$project/build.gradle.kts" ] || die '所选项目根目录缺少 build.gradle 或 build.gradle.kts'
fi
if "$dry_run"; then
    log "[预演] 资源服务器：${SERVER_SCHEME}://${SERVER_ADDR}/"
    log "[预演] Gradle 安装包：$(package_url "$GRADLE_PACKAGE_PATH")"
    log "[预演] 扫描 JDK 8、Gradle ${GRADLE_VERSION}、IDEA 和完整环境变量；修复范围：$scope"
    log '[预演] 缺失项才下载安装；校验受管环境、IDEA、插件并记录前后差异。'
    [ -z "$project" ] || log "[预演] 项目：${project}；检查 IDEA 的项目 SDK、Gradle JVM 和分发，再执行对应 Gradle --no-daemon --console=plain build，失败则整体失败。"
    log '[预演] 本次不安装、不构建、不创建历史目录。'
    exit 0
fi

REPAIR_RUN_DIR=''
final_status=FAILED
failure=0
finished=false
idea_project_pending=false
finish() {
    local code=$?
    trap - EXIT
    if ! "$finished" && [ -n "$REPAIR_RUN_DIR" ] && [ -f "$REPAIR_RUN_DIR/result.tsv" ]; then
        [ "$code" -ne 0 ] || code=1
        audit_finish FAILED "$code" || audit_record_failure "$code" || true
    fi
    exit "$code"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
audit_begin "$scope" "$project"

step_number=0
run_step() {
    local name="$1" logfile results code
    shift
    step_number=$((step_number + 1))
    logfile="$REPAIR_RUN_DIR/logs/$(printf '%02d' "$step_number").log"
    printf '\n正在验证/修复：%s\n' "$name"
    set +e
    /bin/bash "$@" 2>&1 | tee "$logfile"
    results=("${PIPESTATUS[@]}")
    set -e
    code="${results[0]}"
    [ "$code" -ne 0 ] || code="${results[1]}"
    if [ "$code" -eq 0 ]; then
        audit_step "$name" verified 0 "logs/${logfile##*/}" || { failure=1; return 1; }
        return 0
    fi
    audit_step "$name" failed "$code" "logs/${logfile##*/}" || { failure=1; return 1; }
    [ "$failure" -ne 0 ] || failure="$code"
    return "$code"
}

scan_args=()
[ -z "$project" ] || scan_args+=(--project "$project")
log '修复前扫描：'
/bin/bash "$REPO_ROOT/scripts/check-env.sh" ${scan_args[@]+"${scan_args[@]}"} > "$REPAIR_RUN_DIR/before-scan.txt" 2>&1 || true
cat "$REPAIR_RUN_DIR/before-scan.txt"

sdk_ready=true
case "$scope" in
    all|jdk|gradle)
        if ! run_step 'JDK 安装与完整环境配置' "$REPO_ROOT/scripts/runtime/config-jdk.sh"; then sdk_ready=false; fi ;;
esac
case "$scope" in
    all|gradle)
        if "$sdk_ready"; then
            if ! run_step 'Gradle 安装与完整环境配置' "$REPO_ROOT/scripts/runtime/install-gradle.sh"; then sdk_ready=false; fi
        else
            audit_step 'Gradle 安装与完整环境配置' skipped - 'JDK步骤失败'
        fi ;;
esac
idea_ready=true
case "$scope" in
    all|idea)
        if /bin/bash "$REPO_ROOT/scripts/verify-environment.sh" --scope idea > "$REPAIR_RUN_DIR/logs/idea-precheck.log" 2>&1; then
            log 'IDEA 已通过验证，复用现有应用。'
            audit_step 'IDEA 已有应用验证' verified 0 'logs/idea-precheck.log'
        elif ! run_step 'IDEA 安装与应用验证' "$REPO_ROOT/scripts/download-tools.sh" --install-idea; then idea_ready=false; fi ;;
esac
case "$scope" in
    all|plugins)
        if "$idea_ready"; then
            run_step '全部 IDEA 插件安装与验证' "$REPO_ROOT/scripts/software/install-idea-plugins.sh" || true
        else
            audit_step '全部 IDEA 插件安装与验证' skipped - 'IDEA步骤失败'
        fi ;;
esac

run_step '修复后完整验证' "$REPO_ROOT/scripts/verify-environment.sh" --scope "$scope" || true
if [ -n "$project" ]; then
    if "$sdk_ready"; then
        step_number=$((step_number + 1))
        logfile="$REPAIR_RUN_DIR/logs/$(printf '%02d' "$step_number").log"
        log '正在检查：IDEA 项目配置（静态预检，实际同步需在 IDEA 中确认）'
        set +e
        /bin/bash "$REPO_ROOT/scripts/check-idea-project.sh" --project "$project" 2>&1 | tee "$logfile"
        results=("${PIPESTATUS[@]}")
        set -e
        code="${results[0]}"
        if [ "${results[1]}" -ne 0 ]; then code="${results[1]}"; fi
        if [ "$code" -eq 0 ]; then
            audit_step 'IDEA 项目配置预检' static_verified 0 "logs/${logfile##*/}" || failure=1
        elif [ "$code" -eq 2 ] && [ "${results[1]}" -eq 0 ]; then
            idea_project_pending=true
            audit_step 'IDEA 项目配置预检' pending 2 "logs/${logfile##*/}" || failure=1
        else
            audit_step 'IDEA 项目配置预检' failed "$code" "logs/${logfile##*/}" || failure=1
            [ "$failure" -ne 0 ] || failure="$code"
        fi
        run_step '项目构建验证' "$REPO_ROOT/scripts/runtime/verify-gradle.sh" --project "$project" || true
    else
        audit_step '项目构建验证' skipped - 'JDK或Gradle未就绪'
    fi
fi
/bin/bash "$REPO_ROOT/scripts/check-env.sh" ${scan_args[@]+"${scan_args[@]}"} > "$REPAIR_RUN_DIR/after-scan.txt" 2>&1 || true
if [ "$failure" -eq 0 ]; then
    if [ -n "$project" ]; then
        if "$idea_project_pending"; then final_status=PROJECT_BUILD_VERIFIED_IDEA_PENDING
        else final_status=SUCCEEDED; fi
    elif [ "$scope" = all ]; then final_status=ENVIRONMENT_VERIFIED_NO_PROJECT
    else final_status=COMPONENT_VERIFIED; fi
fi
audit_finish "$final_status" "$failure" || {
    failure=1; final_status=FAILED
    audit_record_failure 1 || true
    log '错误：修复历史未能完整保存，本次任务不能标记成功。'
}
finished=true
case "$final_status" in
    SUCCEEDED) log '最终结果：SDK 和终端项目构建验证通过；IDEA 项目静态配置可解析，请启动 IDEA 后重新同步确认。' ;;
    PROJECT_BUILD_VERIFIED_IDEA_PENDING) log '最终结果：SDK 和终端项目构建验证通过；IDEA 项目配置待确认，请按预检中的实际路径设置 JDK、Gradle JVM 和分发，再重新同步。' ;;
    ENVIRONMENT_VERIFIED_NO_PROJECT) log '最终结果：环境验证通过；未选择项目，未执行项目构建。' ;;
    COMPONENT_VERIFIED) log '最终结果：所选组件验证通过；未选择项目，未执行项目构建。' ;;
    *) log '最终结果：失败。安装步骤完成不代表任务成功，请查看失败阶段和修复历史。' ;;
esac
exit "$failure"
