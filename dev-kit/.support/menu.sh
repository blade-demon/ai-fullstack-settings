#!/bin/bash
# 交互菜单显式处理失败，操作失败后仍保留菜单和日志，不直接退出窗口。
set -uo pipefail
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/scripts/lib" && pwd)/common.sh"
log_directory="$HOME/Library/Logs/team-java-env"
operation_count=0
last_operation_status=0

run_logged() {
    local title="$1" logfile results
    shift
    operation_count=$((operation_count + 1))
    if ! (umask 077; mkdir -p "$log_directory"); then
        log "无法创建日志目录：$log_directory"
        return 1
    fi
    logfile="$log_directory/$(date +%Y%m%d-%H%M%S)-$$-${operation_count}.log"
    (umask 077; : > "$logfile") || return 1
    log "正在${title}…"
    /bin/bash "$@" 2>&1 | tee "$logfile"
    results=("${PIPESTATUS[@]}")
    log "日志：$logfile"
    if [ "${results[0]}" -ne 0 ] || [ "${results[1]}" -ne 0 ]; then
        last_operation_status="${results[0]}"
        [ "$last_operation_status" -ne 0 ] || last_operation_status="${results[1]}"
        log '本次操作未完成。可按提示重试，或将日志发给维护者。'
        return "$last_operation_status"
    fi
    last_operation_status=0
}

install_gradle_version() {
    run_logged "安装并配置 Gradle $1" "$REPO_ROOT/scripts/repair-env.sh" --scope gradle --gradle-version "$1"
}

choose_gradle_version() {
    local version_choice
    while :; do
        printf '\n%s\n' '选择 Gradle 版本：' '3.1 Gradle 4.5.1' '3.2 Gradle 6.8' '0. 返回主菜单'
        printf '输入 3.1 / 3.2（也可输入 1 / 2）：'
        if ! IFS= read -r version_choice; then printf '\n'; return 0; fi
        case "$version_choice" in
            1|3.1) install_gradle_version 4.5.1; return $? ;;
            2|3.2) install_gradle_version 6.8; return $? ;;
            0) return 0 ;;
            *) log '请选择 3.1、3.2，或输入 0 返回；尚未开始安装。' ;;
        esac
    done
}

log 'Java 开发环境助手'
log "安装包服务器：${SERVER_SCHEME}://${SERVER_ADDR}"
case "$SERVER_ADDR" in
    127.0.0.1:*|localhost:*) log '当前为本机联调地址；若无法下载，请让维护者提供已配置内网地址的启动包。' ;;
esac
log '环境预检（只读，不下载或安装）：'
/bin/bash "$REPO_ROOT/scripts/check-env.sh" || log '[建议] 按上述待处理项选择菜单；检查不会自动开始安装。'
while :; do
    printf '\n'
    printf '%s\n' '1. 一键安装 JDK、Gradle 并配置环境（包含 IDEA 和全部插件）' '2. 安装并配置 JDK 8' \
        '3. 安装并配置 Gradle' '  3.1 Gradle 4.5.1' '  3.2 Gradle 6.8' \
        "4. 安装 IDEA 软件（安装目录：${IDEA_APP%/*}）" '5. 安装推荐 IDEA 插件' '0. 退出'
    log '一键安装默认版本：JDK 8 + Gradle 4.5.1。'
    printf '输入编号，回车默认选择 1：'
    if ! IFS= read -r choice; then printf '\n'; break; fi
    case "${choice:-1}" in
        1) run_logged '安装并配置全部环境' "$REPO_ROOT/scripts/repair-env.sh" --scope all --gradle-version 4.5.1 ;;
        2) run_logged '安装并配置 JDK 8' "$REPO_ROOT/scripts/repair-env.sh" --scope jdk ;;
        3) choose_gradle_version ;;
        3.1) install_gradle_version 4.5.1 ;;
        3.2) install_gradle_version 6.8 ;;
        4) run_logged '安装 IDEA 软件' "$REPO_ROOT/scripts/repair-env.sh" --scope idea ;;
        5) run_logged '安装推荐 IDEA 插件' "$REPO_ROOT/scripts/repair-env.sh" --scope plugins ;;
        0) break ;;
        *) log '请输入 0 到 5 之间的编号。' ;;
    esac
done
log '已退出，可以关闭此窗口。'
exit "$last_operation_status"
