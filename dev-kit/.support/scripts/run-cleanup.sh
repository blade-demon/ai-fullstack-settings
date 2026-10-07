#!/bin/bash
# 不带菜单的卸载执行层，供原命令行、TUI 预览和交互终端接管共用。
set -uo pipefail
fail() { printf '卸载未启动：%s\n' "$*" >&2; exit 1; }
[ "$(/usr/bin/uname -s)" = Darwin ] || fail '本工具面向 macOS。'
support_dir="$(CDPATH= cd -- "$(/usr/bin/dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)" || exit 1
cleanup_tool="$support_dir/cleanup/cleanup-macos"
manifest="$support_dir/cleanup/manifest.json"
if [ ! -f "$cleanup_tool" ] || [ ! -x "$cleanup_tool" ] || [ -L "$cleanup_tool" ] ||
   [ ! -f "$manifest" ] || [ -L "$manifest" ]; then
    fail '卸载工具不完整，请重新下载完整工具包，并保留同目录的 .support。'
fi
schema="$(/usr/bin/plutil -extract schema raw -o - "$manifest" 2>/dev/null)" || fail '卸载工具校验清单无效，请重新下载。'
[ "$schema" = 1 ] || fail '卸载工具校验清单版本不支持，请重新下载。'
expected="$(/usr/bin/plutil -extract sha256 raw -o - "$manifest" 2>/dev/null)" || fail '卸载工具缺少校验值，请重新下载。'
[[ "$expected" =~ ^[a-fA-F0-9]{64}$ ]] || fail '卸载工具校验值无效，请重新下载。'
actual="$(/usr/bin/shasum -a 256 "$cleanup_tool")" || fail '无法校验卸载工具，请重新下载。'
actual="${actual%% *}"
expected="$(printf '%s' "$expected" | /usr/bin/tr 'A-F' 'a-f')"
[ "$actual" = "$expected" ] || fail '卸载工具校验失败，请重新下载完整工具包。'
# 不添加 --apply / --yes；保留原程序的交互确认和非交互默认预览。
# exec 使中断直接到达原生运行时，避免额外的等待 shell 吞掉信号。
exec "$cleanup_tool" "$@"
