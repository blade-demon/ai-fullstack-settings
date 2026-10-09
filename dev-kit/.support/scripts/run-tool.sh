#!/bin/bash
# 完整工具唯一入口：动作固定，参数始终按列表传递。
set -uo pipefail
scripts="$(CDPATH= cd -- "$(/usr/bin/dirname -- "${BASH_SOURCE[0]}")" && pwd -P)" || exit 1
action="${1:-}"
case "$action" in install|uninstall) shift ;; *) printf '用法：run-tool.sh install|uninstall [选项]\n' >&2; exit 2 ;; esac
cli=false
for argument in "$@"; do
    case "$argument" in
        --plain|--frontend) printf '该入口已移除：%s\n' "$argument" >&2; exit 2 ;;
        --help|-h|--dry-run|--plan-json|--apply|--yes) cli=true ;;
    esac
done
if [ -t 0 ] && [ -t 1 ] && ! "$cli"; then
    case "$action" in install) page=install ;; uninstall) page=cleanup ;; esac
    if [ "$action" = install ] && [ "${TEAM_TOOL_PAGE:-}" = home ]; then page=home; fi
    entry="$scripts/run-tui.sh"
    [ -f "$entry" ] && [ ! -L "$entry" ] || { printf '界面入口缺失，请重新下载工具。\n' >&2; exit 1; }
    exec /bin/bash "$entry" --page "$page" "$@"
fi
case "$action" in install) entry="$scripts/manage-components.sh" ;; uninstall) entry="$scripts/run-cleanup.sh" ;; esac
[ -f "$entry" ] && [ ! -L "$entry" ] || { printf '工具入口缺失，请重新下载。\n' >&2; exit 1; }
exec /bin/bash "$entry" "$@"
