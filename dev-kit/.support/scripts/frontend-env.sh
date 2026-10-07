#!/bin/bash
# 前端环境独立调度；每个组件返回验证结果，任何失败均保留非零状态。
set -euo pipefail
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/lib" && pwd)/common.sh"
component=all
node_version=all
preview=false
while [ "$#" -gt 0 ]; do
    case "$1" in
        --component|--node-version)
            [ "$#" -ge 2 ] && [ -n "$2" ] || die "$1 后需要值"
            if [ "$1" = --component ]; then component="$2"; else node_version="$2"; fi
            shift 2 ;;
        --dry-run) preview=true; shift ;;
        --help|-h)
            log '用法：frontend-env.sh [--component all|node|iterm2|zsh] [--node-version 14|16|18|all] [--dry-run]'
            log '独立安装前端环境；不改变 Java 一键安装范围。'; exit 0 ;;
        *) die "未知参数：$1" ;;
    esac
done
case "$component" in all|node|iterm2|zsh) ;; *) die '无效的前端组件' ;; esac
case "$node_version" in all|14|16|18) ;; *) die 'Node 版本请选择 14、16、18 或 all' ;; esac

run_dir=''
failure=0
finish() {
    local status=$?
    trap - EXIT
    if [ -n "$run_dir" ]; then
        [ "$status" -ne 0 ] || status="$failure"
        local final=FAILED
        [ "$status" -ne 0 ] || final=SUCCEEDED
        printf 'status\texit_code\tcomponent\tnode_version\n%s\t%s\t%s\t%s\n' \
            "$final" "$status" "$component" "$node_version" > "$run_dir/result.tsv" || status=1
        log "前端环境记录：$run_dir"
    fi
    exit "$status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if ! "$preview"; then
    log_root="$HOME/Library/Logs/team-java-env/frontend"
    (umask 077; mkdir -p "$log_root")
    run_dir="$(umask 077; mktemp -d "$log_root/$(date +%Y%m%d-%H%M%S)-XXXXXX")"
    printf 'component\tstatus\texit_code\tlog\n' > "$run_dir/steps.tsv"
fi

run_component() {
    local name="$1" script="$2" code results args=()
    shift 2
    args=("$@")
    if "$preview"; then
        /bin/bash "$REPO_ROOT/scripts/$script" ${args[@]+"${args[@]}"} --dry-run
        return
    fi
    log "正在安装和验证：$name"
    team_tui_stage "frontend-$name" running "$name"
    set +e
    /bin/bash "$REPO_ROOT/scripts/$script" ${args[@]+"${args[@]}"} 2>&1 | tee "$run_dir/$name.log"
    results=("${PIPESTATUS[@]}")
    set -e
    code="${results[0]}"
    [ "$code" -ne 0 ] || code="${results[1]}"
    if [ "$code" -eq 0 ]; then
        team_tui_stage "frontend-$name" succeeded "$name"
        printf '%s\tverified\t0\t%s.log\n' "$name" "$name" >> "$run_dir/steps.tsv"
    else
        team_tui_stage "frontend-$name" failed "$name"
        printf '%s\tfailed\t%s\t%s.log\n' "$name" "$code" "$name" >> "$run_dir/steps.tsv"
        [ "$failure" -ne 0 ] || failure="$code"
    fi
}

case "$component" in all|node) run_component node runtime/install-node.sh --version "$node_version" ;; esac
case "$component" in all|iterm2) run_component iterm2 software/install-iterm2.sh ;; esac
case "$component" in all|zsh) run_component zsh software/install-zsh.sh ;; esac
if "$preview"; then log '前端环境预览结束，未执行安装。'
elif [ "$failure" -eq 0 ]; then log '前端环境安装验证通过；请新开终端加载配置。'
else log '前端环境有组件失败，请查看对应日志后重试。'; fi
exit "$failure"
