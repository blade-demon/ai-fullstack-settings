#!/bin/bash
# 成员独立卸载入口；执行包内自带运行时的工具，无需系统 Python。
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

pause_on_exit=false
pause_on_failure=false
if [ "$argument_count" -eq 0 ] && [ -t 0 ] && [ -t 1 ]; then
    if "$plain"; then pause_on_exit=true; else pause_on_failure=true; fi
fi
finish() {
    local status=$?
    trap - EXIT
    if [ "$status" -ne 129 ] && [ "$status" -ne 130 ] && [ "$status" -ne 143 ] &&
       { "$pause_on_exit" || { "$pause_on_failure" && [ "$status" -ne 0 ]; }; }; then
        printf '\n请查看上面的卸载结果。按回车关闭窗口…'
        IFS= read -r answer || true
    fi
    exit "$status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

if ! "$plain" && [ "$argument_count" -eq 0 ] && [ -t 0 ] && [ -t 1 ]; then
    helper="$kit_dir/.support/scripts/run-tui.sh"
    if [ ! -f "$helper" ] || [ -L "$helper" ]; then
        printf '%s\n' '界面未启动：工具包不完整，请重新下载完整工具包；也可使用 --plain 进入原命令行模式。' >&2
        exit 1
    fi
    # Ctrl-C belongs to the foreground TUI/uninstaller; do not overwrite the
    # TUI's later result after it resumes from ExecProcess.
    trap ':' INT
    /bin/bash "$helper" --page cleanup
else
    helper="$kit_dir/.support/scripts/run-cleanup.sh"
    if [ ! -f "$helper" ] || [ -L "$helper" ]; then
        printf '%s\n' '卸载未启动：工具包不完整，请重新下载完整工具包，并保留同目录的 .support。' >&2
        exit 1
    fi
    # 不展开 Bash 3.2 的空数组，也不添加 --apply / --yes。
    if [ "$argument_count" -gt 0 ]; then
        /bin/bash "$helper" "${arguments[@]}"
    else
        /bin/bash "$helper"
    fi
fi
exit "$?"
