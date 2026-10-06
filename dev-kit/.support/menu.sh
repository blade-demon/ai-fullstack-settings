#!/bin/bash
# 交互菜单显式处理失败，操作失败后仍保留菜单和日志，不直接退出窗口。
set -uo pipefail
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/scripts/lib" && pwd)/common.sh"
selected_project=''
log_directory="$HOME/Library/Logs/team-java-env"
operation_count=0
last_operation_status=0

run_logged() {
    local report_only=false
    if [ "${1:-}" = --check ]; then report_only=true; shift; fi
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
        if "$report_only" && [ "${results[0]}" -eq 1 ] && [ "${results[1]}" -eq 0 ]; then
            log '检查中有待安装或待确认项，请按上面的提示处理。'
            last_operation_status=0
            return 0
        fi
        last_operation_status="${results[0]}"
        [ "$last_operation_status" -ne 0 ] || last_operation_status="${results[1]}"
        log '本次操作未完成。可按提示重试，或将日志发给维护者。'
        return "$last_operation_status"
    fi
    last_operation_status=0
}

choose_project() {
    local chosen selection_log
    local cancel_message="${1:-已取消选择，返回菜单。}"
    if ! command -v osascript >/dev/null 2>&1; then
        log '无法打开系统目录选择器。请联系维护者，或使用 --project 命令行入口。'
        return 1
    fi
    if ! chosen="$(osascript -e 'POSIX path of (choose folder with prompt "请选择 Gradle 项目根目录（包含 build.gradle 或 build.gradle.kts）")' 2>&1)"; then
        case "$chosen" in
            *'(-128)'*) log "$cancel_message" ;;
            *)
                log '无法打开项目选择窗口。请按下面的错误信息联系维护者：'
                log "$chosen"
                selection_log="$log_directory/$(date +%Y%m%d-%H%M%S)-$$-folder.log"
                if (umask 077; mkdir -p "$log_directory" && printf '%s\n' "$chosen" > "$selection_log"); then
                    log "日志：$selection_log"
                fi
                ;;
        esac
        return 1
    fi
    [ -n "$chosen" ] || return 1
    selected_project="${chosen%/}"
}

configure_environment() {
    local args=(--scope all)
    [ -z "$selected_project" ] || args+=(--project "$selected_project")
    if [ -z "$selected_project" ]; then
        log '未选择项目：本次仅修复和验证环境，不会宣称项目构建通过。可先用菜单 3 选择项目。'
    else
        log "本次必须完成项目构建验证：$selected_project"
    fi
    run_logged '一键修复与结果验证' "$REPO_ROOT/scripts/repair-env.sh" "${args[@]}"
}

check_environment() {
    log '可选择一个项目用于后续构建验证；本次仅扫描，取消则保留之前的项目或仅检查本机。'
    choose_project '未更换项目，继续检查现有选择或本机环境。' || true
    local args=()
    [ -z "$selected_project" ] || args+=(--project "$selected_project")
    run_logged --check '检查环境' "$REPO_ROOT/scripts/check-env.sh" ${args[@]+"${args[@]}"}
}

install_gradle() {
    log "将安装或复用独立 Gradle ${GRADLE_VERSION} 并修复完整环境变量。"
    log '选择项目后默认执行 build（不跳过测试）；取消选择则保留此前选择，初次取消仅修复Gradle环境。'
    choose_project '未选择新项目，保留当前选择。' || true
    local args=(--scope gradle)
    [ -z "$selected_project" ] || args+=(--project "$selected_project")
    run_logged 'Gradle 修复与构建验证' "$REPO_ROOT/scripts/repair-env.sh" "${args[@]}"
}

start_mysql() {
    local password
    if ! command -v docker >/dev/null 2>&1; then
        log '本地数据库需要 Docker Desktop。请先安装并打开它；JDK/Gradle 配置不受影响。'
        return 1
    fi
    if ! docker info >/dev/null 2>&1; then
        log 'Docker 尚未启动。请打开 Docker Desktop，等待就绪后再试。'
        return 1
    fi
    log "将启动本地数据库（${MYSQL_IMAGE:-mysql:8.0}）。如与团队版本不同，请先联系维护者。"
    log '首次启动使用下方密码创建 root 账号；已有数据卷不会因重新输入密码而重置。'
    printf '请输入本地数据库密码（输入时不显示，直接回车取消）：'
    IFS= read -r -s password || return 1
    printf '\n'
    if [ -z "$password" ]; then log '已取消启动。'; return 0; fi
    if MYSQL_ROOT_PASSWORD="$password" run_logged '启动本地数据库' "$REPO_ROOT/scripts/services/mysql.sh" up; then
        log "容器已启动；数据库初始化可能还需一会儿。地址：127.0.0.1:${MYSQL_PORT:-3306}，用户：root，数据库：${MYSQL_DATABASE:-app_dev}。"
    fi
    unset password
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
    log "当前构建验证项目：${selected_project:-未选择（可用菜单 3 选择）}"
    printf '%s\n' '1. 一键修复缺失环境并验证（推荐，包含全部插件）' '2. 修复 JDK 8 和完整环境变量' \
        '3. 检查环境（可选择项目）' '4. 启动本地 MySQL（可选）' '5. 停止本地 MySQL（保留数据）' \
        '6. 下载开发软件 / IDEA 插件' "7. 单独配置并安装 Gradle ${GRADLE_VERSION}" \
        '8. 修复 IDEA（~/Applications）' '9. 一键安装并验证全部 IDEA 插件' '10. 查看安装修复历史' '0. 退出'
    printf '输入编号，回车默认选择 1：'
    if ! IFS= read -r choice; then printf '\n'; break; fi
    case "${choice:-1}" in
        1) configure_environment ;;
        2) run_logged '修复 JDK 8' "$REPO_ROOT/scripts/repair-env.sh" --scope jdk ;;
        3) check_environment ;;
        4) start_mysql ;;
        5) run_logged '停止本地数据库' "$REPO_ROOT/scripts/services/mysql.sh" down ;;
        6) run_logged '下载软件或插件' "$REPO_ROOT/scripts/download-tools.sh" ;;
        7) install_gradle ;;
        8) run_logged '修复 IDEA' "$REPO_ROOT/scripts/repair-env.sh" --scope idea ;;
        9) run_logged '安装全部 IDEA 插件' "$REPO_ROOT/scripts/repair-env.sh" --scope plugins ;;
        10) /bin/bash "$REPO_ROOT/scripts/history.sh" ;;
        0) break ;;
        *) log '请输入 0 到 10 之间的编号。' ;;
    esac
done
log '已退出，可以关闭此窗口。'
exit "$last_operation_status"
