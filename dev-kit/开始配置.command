#!/bin/bash
# macOS Finder 双击入口；不要单独移动此文件，保留同目录的 .support。
set -uo pipefail
kit_dir="$(CDPATH= cd -- "$(/usr/bin/dirname -- "${BASH_SOURCE[0]}")" && pwd -P)" || exit 1
plain=false
argument_count=0
arguments=()
for argument in "$@"; do
    if [ "$argument" = --plain ]; then
        plain=true
    else
        arguments[argument_count]="$argument"
        argument_count=$((argument_count + 1))
    fi
done

# Bash 3.2 的 nounset 不能展开空数组；只在有业务参数时读取 arguments。
tui_page=''
if ! "$plain" && [ -t 0 ] && [ -t 1 ]; then
    if [ "$argument_count" -eq 0 ]; then
        tui_page=home
    elif [ "$argument_count" -eq 1 ] && [ "${arguments[0]}" = --frontend ]; then
        tui_page=frontend
    fi
fi
if [ -n "$tui_page" ]; then
    helper="$kit_dir/.support/scripts/run-tui.sh"
    if [ ! -f "$helper" ] || [ -L "$helper" ]; then
        printf '%s\n' '界面未启动：工具包不完整，请重新下载完整工具包；也可使用 --plain 进入原命令行模式。' >&2
        result=1
    else
        trap ':' INT
        /bin/bash "$helper" --page "$tui_page"
        result=$?
    fi
elif [ "$argument_count" -gt 0 ]; then
    exec /bin/bash "$kit_dir/.support/install_env.sh" "${arguments[@]}"
elif "$plain"; then
    /bin/bash "$kit_dir/.support/menu.sh"
    result=$?
elif [ ! -t 0 ] || [ ! -t 1 ]; then
    printf '%s\n' '请双击「开始配置.command」打开菜单。' \
        '命令行可用：bash 开始配置.command --dry-run 或 --project 项目路径。' \
        '使用 --plain 可打开原 Bash 菜单。'
    exit 0
fi
if [ "$result" -ne 0 ] && [ "$result" -ne 129 ] && [ "$result" -ne 130 ] && [ "$result" -ne 143 ] && [ -t 0 ] && [ -t 1 ]; then
    printf '\n工具未能完成操作，请将上面的信息发给维护者。\n按回车关闭…'
    IFS= read -r answer || true
fi
exit "$result"
