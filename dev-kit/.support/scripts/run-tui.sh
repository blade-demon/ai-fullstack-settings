#!/bin/bash
# 校验包内原生界面后启动；成员无需安装 Go 或 Python。
set -uo pipefail
fail() {
    printf '界面未启动：%s\n' "$*" >&2
    printf '%s\n' '请重新运行 devtool-helper.sh 获取完整工具，并使用交互终端。' >&2
    exit 1
}
page=home
options=()
while [ "$#" -gt 0 ]; do
    case "$1" in
        --page)
            [ "$#" -ge 2 ] || { printf '%s\n' '用法：run-tui.sh --page home|frontend|cleanup' >&2; exit 2; }
            page="$2"
            shift 2
            ;;
        --components|--gradle-version|--node-version)
            [ "$#" -ge 2 ] && [ -n "$2" ] || { printf '参数缺少值：%s\n' "$1" >&2; exit 2; }
            options+=("$1" "$2"); shift 2 ;;
        *) printf '%s\n' '用法：run-tui.sh --page home|install|cleanup [组件与版本选项]' >&2; exit 2 ;;
    esac
done
case "$page" in home|install|cleanup) ;; *) printf '%s\n' '不支持的界面页面。' >&2; exit 2 ;; esac
[ "$(/usr/bin/uname -s)" = Darwin ] || fail '本工具面向 macOS。'
case "$(/usr/bin/uname -m)" in
    arm64) arch=arm64 ;;
    x86_64) arch=amd64 ;;
    *) fail '不支持当前处理器架构。' ;;
esac
support_dir="$(CDPATH= cd -- "$(/usr/bin/dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)" || fail '无法定位支持目录。'
manifest="$support_dir/tui/manifest.json"
[ -f "$manifest" ] && [ ! -L "$manifest" ] || fail '界面校验清单缺失或无效。'
schema="$(/usr/bin/plutil -extract schema raw -o - "$manifest" 2>/dev/null)" || fail '界面校验清单无效。'
[ "$schema" = 1 ] || fail '界面校验清单版本不支持。'
file="$(/usr/bin/plutil -extract "binaries.$arch.file" raw -o - "$manifest" 2>/dev/null)" || fail '界面校验清单缺少当前架构。'
[ "$file" = "team-dev-env-$arch" ] || fail '界面文件名无效。'
binary="$support_dir/tui/$file"
[ -f "$binary" ] && [ -x "$binary" ] && [ ! -L "$binary" ] || fail '界面程序缺失、不可执行或无效。'
expected="$(/usr/bin/plutil -extract "binaries.$arch.sha256" raw -o - "$manifest" 2>/dev/null)" || fail '界面程序缺少校验值。'
[[ "$expected" =~ ^[a-fA-F0-9]{64}$ ]] || fail '界面程序校验值无效。'
actual="$(/usr/bin/shasum -a 256 "$binary")" || fail '无法校验界面程序。'
actual="${actual%% *}"
expected="$(printf '%s' "$expected" | /usr/bin/tr 'A-F' 'a-f')"
[ "$actual" = "$expected" ] || fail '界面程序校验失败。'
exec "$binary" --support-dir "$support_dir" --page "$page" ${options[@]+"${options[@]}"}
