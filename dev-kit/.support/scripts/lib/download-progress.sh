#!/bin/bash
# 真实下载字节；没有可靠 Content-Length 时总量为 0。
team_download() (
    destination="$1" url="$2"; shift 2
    if [ "${TEAM_TUI_EVENTS:-0}" != 1 ]; then
        exec curl --disable --fail --location --silent --show-error --proto '=http,https' --proto-redir '=http,https' --output "$destination" "$@" -- "$url"
    fi
    headers="$(mktemp "${TMPDIR:-/tmp}/team-download-headers.XXXXXXXX")" || exit 1
    transfer_pid='' attempt="${TEAM_DOWNLOAD_ATTEMPT:-1}" previous=0
    resource="${TEAM_TUI_RESOURCE:-${url##*/}}"
    resource="${resource//$'\t'/ }"; resource="${resource//$'\r'/ }"; resource="${resource//$'\n'/ }"
    cleanup_transfer() {
        status=$?; trap - EXIT
        if [ -n "$transfer_pid" ]; then kill "$transfer_pid" 2>/dev/null || true; wait "$transfer_pid" 2>/dev/null || true; fi
        rm -f -- "$headers"
        exit "$status"
    }
    trap cleanup_transfer EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP
    progress() {
        completed=0
        [ ! -f "$destination" ] || completed="$(/usr/bin/stat -f '%z' "$destination" 2>/dev/null || printf 0)"
        case "$completed" in ''|*[!0-9]*) completed=0 ;; esac
        total="$(awk '
            /^HTTP\// {code=$2; size=0; invalid=0}
            {line=tolower($0); sub(/\r$/, "", line)}
            line ~ /^content-length:[[:space:]]*[0-9]+$/ {sub(/^content-length:[[:space:]]*/, "", line); size=line}
            line ~ /^content-encoding:/ && line !~ /identity/ {invalid=1}
            line ~ /^transfer-encoding:/ {invalid=1}
            END {if(code==200 && !invalid) printf "%.0f", size; else print 0}
        ' "$headers")"
        case "$total" in ''|*[!0-9]*) total=0 ;; esac
        [ "$completed" -le "$total" ] || total=0
        if [ "$completed" -lt "$previous" ]; then attempt=$((attempt + 1)); fi
        previous="$completed"
        printf '@@TEAM_TUI\tprogress\t%s\t%s\t%s\t%s\t%s\n' "${TEAM_TUI_COMPONENT:-download}" "$resource" "$attempt" "$completed" "$total"
    }
    curl --disable --fail --location --silent --show-error --proto '=http,https' --proto-redir '=http,https' \
        --dump-header "$headers" --output "$destination" "$@" -- "$url" &
    transfer_pid=$!
    while kill -0 "$transfer_pid" 2>/dev/null; do progress; sleep 0.2; done
    code=0; wait "$transfer_pid" || code=$?
    transfer_pid=''
    progress
    if [ "$code" -eq 0 ]; then
        printf '@@TEAM_TUI\tstage\t%s:transfer:%s\tsucceeded\t资源传输完成\n' "${TEAM_TUI_COMPONENT:-download}" "$resource"
    fi
    exit "$code"
)
