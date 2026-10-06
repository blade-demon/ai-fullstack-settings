#!/bin/bash
# macOS Finder 双击入口；不要单独移动此文件，保留同目录的 .support。
set -uo pipefail
kit_dir="$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 1
if [ "$#" -gt 0 ]; then
    exec /bin/bash "$kit_dir/.support/install_env.sh" "$@"
fi
if [ ! -t 0 ]; then
    printf '%s\n' '请双击「开始配置.command」打开菜单。' \
        '命令行可用：bash 开始配置.command --dry-run 或 --project 项目路径。'
    exit 0
fi
/bin/bash "$kit_dir/.support/menu.sh"
result=$?
if [ "$result" -ne 0 ]; then
    printf '\n工具未能完成操作，请将上面的信息发给维护者。\n按回车关闭…'
    IFS= read -r answer || true
fi
exit "$result"
