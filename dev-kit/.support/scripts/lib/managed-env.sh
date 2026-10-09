#!/bin/bash
# 由调用方加载 common.sh。旧 env.sh 的内容原样保留，仅更新显式受管区块。
# 模块与聚合文件首次发生变更时保存 .bak，不覆盖其他模块或用户自定义设置。

managed_env_prepare_paths() {
    JDK_ENV_FILE="${JDK_ENV_FILE:-${ENV_FILE%/*}/jdk.sh}"
    GRADLE_ENV_FILE="${GRADLE_ENV_FILE:-${ENV_FILE%/*}/gradle.sh}"
    if [ -z "${SHELL_PROFILE:-}" ]; then
        case "${SHELL:-/bin/zsh}" in
            */zsh) SHELL_PROFILE="$HOME/.zshrc" ;;
            */bash) SHELL_PROFILE="$HOME/.bash_profile" ;;
            *) die '请设置 SHELL_PROFILE 为 Bash/Zsh 配置文件路径' ;;
        esac
    fi
    GRADLE_DEFAULT_FILE="${GRADLE_DEFAULT_FILE:-${ENV_FILE%/*}/gradle-default}"
    local file other parent
    for file in "$ENV_FILE" "$JDK_ENV_FILE" "$GRADLE_ENV_FILE" "$GRADLE_DEFAULT_FILE" "$SHELL_PROFILE"; do
        require_absolute_path '受管环境路径' "$file"
        parent="$(dirname -- "$file")"
        while [ "$parent" != / ]; do
            [ ! -e "$parent" ] || [ -d "$parent" ] || die "环境配置目录位置已有其他文件：$parent"
            parent="$(dirname -- "$parent")"
        done
        [ ! -L "$file" ] || die "环境文件是符号链接，原文件已保留：$file"
        if [ -e "$file" ] && [ ! -f "$file" ]; then die "环境路径不是普通文件：$file"; fi
    done
    [ "$ENV_FILE" != "$JDK_ENV_FILE" ] && [ "$ENV_FILE" != "$GRADLE_ENV_FILE" ] &&
        [ "$JDK_ENV_FILE" != "$GRADLE_ENV_FILE" ] || die 'JDK、Gradle 模块与聚合环境文件必须使用不同路径'
    for file in "$ENV_FILE" "$JDK_ENV_FILE" "$GRADLE_ENV_FILE"; do
        [ "$file" != "$SHELL_PROFILE" ] || die '环境文件不能与 SHELL_PROFILE 相同'
        [ "$file" != "$GRADLE_DEFAULT_FILE" ] || die 'Gradle 默认数据文件不能覆盖环境模块'
    done
    [ "$GRADLE_DEFAULT_FILE" != "$SHELL_PROFILE" ] || die 'Gradle 默认数据文件不能覆盖 Shell 配置'
}

# 真实预检与安装共用；不下载、不创建用户目录、不加载用户 profile。
managed_install_target_check() {
    local target="$1" kind="$2" marker="$1/.team-java-env-install.json" parent="$1"
    while [ "$parent" != / ]; do
        [ ! -e "$parent" ] || [ -d "$parent" ] || die "安装目录位置已有其他文件：$parent"
        parent="$(dirname -- "$parent")"
    done
    [ ! -L "$target" ] || die "安装目录是符号链接，原内容已保留：$target"
    if [ -e "$marker" ] || [ -L "$marker" ]; then
        [ -f "$marker" ] && [ ! -L "$marker" ] || die "安装来源标记不是普通文件：$marker"
        [ "$(plutil -extract schema raw -o - "$marker" 2>/dev/null)" = 1 ] &&
            [ "$(plutil -extract tool raw -o - "$marker" 2>/dev/null)" = team-java-env ] &&
            [ "$(plutil -extract kind raw -o - "$marker" 2>/dev/null)" = "$kind" ] || die "安装来源标记无效，原目录已保留：$target"
    fi
}

managed_env_profile_ready() {
    local profile="${SHELL_PROFILE:-}" environment="${ENV_FILE:-$HOME/.config/java-dev/env.sh}" line
    if [ -z "$profile" ]; then
        case "${SHELL:-/bin/zsh}" in */zsh) profile="$HOME/.zshrc" ;; */bash) profile="$HOME/.bash_profile" ;; *) return 1 ;; esac
    fi
    [ -f "$profile" ] && [ ! -L "$profile" ] || return 1
    line=". $(shell_quote "$environment")"
    # A source earlier in the file can be overridden by SDK managers or later exports.
    MANAGED_SOURCE_LINE="$line" awk '
        { first=second; second=last; last=$0 }
        END {
            expected=ENVIRON["MANAGED_SOURCE_LINE"]
            if (last==expected) exit 0
            if (first=="# >>> team-java-env managed >>>" && second==expected &&
                last=="# <<< team-java-env managed <<<") exit 0
            exit 1
        }
    ' "$profile"
}

_managed_env_profile_values() (
    # Final repair verification only. Startup probes must never execute the profile.
    set +e
    local profile="${SHELL_PROFILE:-}" shell work runner='' watchdog='' status=1
    local shell_args=()
    case "${SHELL:-/bin/zsh}" in
        */bash) shell=/bin/bash; shell_args=(--noprofile --norc); [ -n "$profile" ] || profile="$HOME/.bash_profile" ;;
        */zsh) shell=/bin/zsh; shell_args=(-d -f); [ -n "$profile" ] || profile="$HOME/.zshrc" ;;
        *) exit 1 ;;
    esac
    [ -f "$profile" ] && [ ! -L "$profile" ] || exit 1
    work="$(umask 077; mktemp -d "${TMPDIR:-/tmp}/profile-verify.XXXXXXXX")" || exit 1
    cleanup_profile_verification() {
        if [ -n "$watchdog" ]; then
            kill -TERM -- "-$watchdog" 2>/dev/null || true
            wait "$watchdog" 2>/dev/null || true
        fi
        if [ -n "$runner" ]; then
            kill -TERM -- "-$runner" 2>/dev/null || true
            kill -KILL -- "-$runner" 2>/dev/null || true
            wait "$runner" 2>/dev/null || true
        fi
        rm -rf -- "$work"
    }
    trap cleanup_profile_verification EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    # Give each child an isolated process group so timeout cleanup includes its children.
    set -m
    /usr/bin/env -i HOME="$HOME" SHELL="$shell" PATH='/usr/bin:/bin:/usr/sbin:/sbin' \
        "$shell" "${shell_args[@]}" -c '
            . "$1" >/dev/null 2>&1 || exit 1
            case "$2" in 6.8) gradle_alias="${GRADLE_6_8_HOME:-}" ;; *) gradle_alias="${GRADLE_4_5_1_HOME:-}" ;; esac
            builtin printf "%s\0" "${JAVA_HOME:-}" "${JAVA_8_HOME:-}" "${JRE_HOME:-}" \
                "${GRADLE_HOME:-}" "$gradle_alias" "${GRADLE_USER_HOME:-}" "${PATH:-}" \
                "$(command -v java 2>/dev/null || true)" "$(command -v gradle 2>/dev/null || true)"
        ' verify-profile "$profile" "$GRADLE_VERSION" </dev/null > "$work/values" 2>/dev/null &
    runner=$!
    (
        /bin/sleep 5
        : > "$work/timed-out"
        kill -TERM -- "-$runner" 2>/dev/null || true
        /bin/sleep 1
        kill -KILL -- "-$runner" 2>/dev/null || true
    ) >/dev/null 2>&1 &
    watchdog=$!
    wait "$runner" 2>/dev/null
    status=$?
    kill -TERM -- "-$watchdog" 2>/dev/null || true
    wait "$watchdog" 2>/dev/null || true
    watchdog=''
    [ "$status" -eq 0 ] && [ ! -e "$work/timed-out" ] || exit 1
    cat "$work/values"
)

_managed_env_write_block() (
    local target="$1" body="$2" at_end="${3:-false}" temporary='' block='' input="$1"
    local start='# >>> team-java-env managed >>>' end='# <<< team-java-env managed <<<'
    mkdir -p -- "$(dirname -- "$target")" || die "无法创建环境配置目录：$target"
    temporary="$(mktemp "$target.tmp.XXXXXXXX")" || die "无法创建环境临时文件：$target"
    trap 'rm -f -- "$temporary"; [ -z "$block" ] || rm -f -- "$block"' EXIT
    if [ -f "$target" ]; then cp -p -- "$target" "$temporary"; else input=/dev/null; fi
    block="$(mktemp "$target.block.XXXXXXXX")" || die "无法创建环境区块临时文件：$target"
    printf '%s\n%s\n%s\n' "$start" "$body" "$end" > "$block"
    # 用文件传递区块正文，避免 awk -v 对反斜线/引号进行二次解释。
    MANAGED_BLOCK_FILE="$block" awk -v start="$start" -v end="$end" -v at_end="$at_end" '
        function emit(    line) {
            while ((getline line < ENVIRON["MANAGED_BLOCK_FILE"]) > 0) print line
            close(ENVIRON["MANAGED_BLOCK_FILE"])
        }
        $0 == start {if (inside || written) exit 2; inside=1; if (at_end!="true") emit(); written=1; next}
        $0 == end {if (!inside) exit 2; inside=0; next}
        !inside {print}
        END {if (inside) exit 2; if (!written || at_end=="true") {if (NR) print ""; emit()}}
    ' "$input" > "$temporary" || die "环境文件受管区块不完整，原文件已保留：$target"
    if [ -f "$target" ] && cmp -s "$target" "$temporary"; then
        log "环境配置已一致：$target"
        exit 0
    fi
    if [ -f "$target" ] && [ ! -e "$target.bak" ] && [ ! -L "$target.bak" ]; then
        cp -p -- "$target" "$target.bak" || die "无法备份环境文件：$target"
        log "已备份：$target.bak"
    fi
    [ ! -L "$target" ] || die "写入前环境文件变成了符号链接，已保留：$target"
    mv -f -- "$temporary" "$target" || die "无法保存环境配置：$target"
    log "已更新环境配置：$target"
)

_managed_env_path_body() {
    cat <<'ENV'
_team_java_env_path() {
    local remaining="${PATH-}" entry cleaned='' separator='' more prefix='' java_bin='' gradle_bin=''
    [ -z "${JAVA_HOME:-}" ] || java_bin="$JAVA_HOME/bin"
    [ -z "${GRADLE_HOME:-}" ] || gradle_bin="$GRADLE_HOME/bin"
    while :; do
        case "$remaining" in
            *:*) entry="${remaining%%:*}"; remaining="${remaining#*:}"; more=1 ;;
            *) entry="$remaining"; more=0 ;;
        esac
        if ! { [ -n "$java_bin" ] && { [ "$entry" = "$java_bin" ] || [ "$entry" -ef "$java_bin" ]; }; } &&
           ! { [ -n "$gradle_bin" ] && { [ "$entry" = "$gradle_bin" ] || [ "$entry" -ef "$gradle_bin" ]; }; }; then
            cleaned="${cleaned}${separator}${entry}"
            separator=':'
        fi
        [ "$more" -eq 1 ] || break
    done
    [ -z "$java_bin" ] || prefix="$java_bin"
    [ -z "$gradle_bin" ] || prefix="${prefix:+${prefix}:}$gradle_bin"
    if [ -n "$prefix" ]; then export PATH="${prefix}${separator}${cleaned}"; fi
}
_team_java_env_path
unset -f _team_java_env_path
ENV
}

_managed_env_finish() {
    local body source_line path_body
    body="$(printf '[ ! -f %s ] || . %s\n[ ! -f %s ] || . %s\n' \
        "$(shell_quote "$JDK_ENV_FILE")" "$(shell_quote "$JDK_ENV_FILE")" \
        "$(shell_quote "$GRADLE_ENV_FILE")" "$(shell_quote "$GRADLE_ENV_FILE")")"
    path_body="$(_managed_env_path_body)"
    body="$body
$path_body"
    _managed_env_write_block "$ENV_FILE" "$body"
    source_line=". $(shell_quote "$ENV_FILE")"
    if managed_env_profile_ready; then
        log "Shell 入口已配置：$SHELL_PROFILE"
    else
        _managed_env_write_block "$SHELL_PROFILE" "$source_line" true
    fi
    log "当前终端可执行：$source_line"
}

managed_env_write_jdk() {
    local java_home="$1" body
    [ -d "$java_home/jre" ] || die "JDK 8 缺少实际 jre 目录，无法配置 JRE_HOME：$java_home/jre"
    managed_env_prepare_paths
    body="$(printf 'export JAVA_HOME=%s\nexport JAVA_8_HOME=%s\nexport JRE_HOME=%s\n' \
        "$(shell_quote "$java_home")" "$(shell_quote "$java_home")" "$(shell_quote "$java_home/jre")")"
    _managed_env_write_block "$JDK_ENV_FILE" "$body"
    _managed_env_finish
}

# 保留已验证版本的别名，让切换后的新终端仍能找到另一套 SDK。
managed_env_saved_value() {
    [ -f "$ENV_FILE" ] || return 0
    /usr/bin/env -i HOME="$HOME" PATH='/usr/bin:/bin:/usr/sbin:/sbin' /bin/bash -c '
        source "$1" >/dev/null 2>&1 || exit 1
        name="$2"; printf "%s" "${!name-}"
    ' saved-value "$ENV_FILE" "$1"
}

managed_env_write_gradle() {
    local gradle_home="$1" body other alias previous
    managed_env_prepare_paths
    require_absolute_path GRADLE_USER_HOME "$GRADLE_USER_HOME"
    body="$(printf 'export GRADLE_HOME=%s\nexport GRADLE_USER_HOME=%s\nexport %s=%s\n' \
        "$(shell_quote "$gradle_home")" "$(shell_quote "$GRADLE_USER_HOME")" \
        "$(gradle_alias_name)" "$(shell_quote "$gradle_home")")"
    for other in 4.5.1 6.8; do
        [ "$other" != "$GRADLE_VERSION" ] || continue
        alias="$(gradle_alias_name "$other")"
        previous="$(managed_env_saved_value "$alias")" || previous=''
        if [ -x "$previous/bin/gradle" ] && [ -s "$previous/lib/gradle-launcher-$other.jar" ]; then
            body="$body
export $alias=$(shell_quote "$previous")"
        fi
    done
    body="$body
export GRADLE_DEFAULT_FILE=$(shell_quote "$GRADLE_DEFAULT_FILE")
$(_managed_gradle_switch_body)"
    _managed_env_write_block "$GRADLE_ENV_FILE" "$body"
    if [ "${GRADLE_REGISTER_ONLY:-0}" != 1 ]; then
        (source "$GRADLE_ENV_FILE"; gradle_use "$GRADLE_VERSION" --default >/dev/null) || die '无法保存 Gradle 默认版本'
    fi
    _managed_env_finish
}

_managed_gradle_switch_body() {
    cat <<'GRADLE_SWITCH'
gradle_use() {
    local requested="${1:-}" persist="${2:-}" target='' old_bin="${GRADLE_HOME:+$GRADLE_HOME/bin}"
    local remaining="${PATH-}" part cleaned='' separator='' more temporary='' probe
    if [ "$requested" = --list ] && [ "$#" -eq 1 ]; then
        printf '4.5.1: %s\n6.8: %s\n当前终端: %s\n' "${GRADLE_4_5_1_HOME:-未安装}" "${GRADLE_6_8_HOME:-未安装}" "${GRADLE_HOME:-未选择}"
        if [ -f "$GRADLE_DEFAULT_FILE" ] && [ ! -L "$GRADLE_DEFAULT_FILE" ]; then printf '新终端默认: '; cat "$GRADLE_DEFAULT_FILE"; fi
        return 0
    fi
    case "$requested" in 4.5.1) target="${GRADLE_4_5_1_HOME:-}" ;; 6.8) target="${GRADLE_6_8_HOME:-}" ;; *) printf '用法：gradle_use 4.5.1|6.8 [--default]；gradle_use --list\n' >&2; return 2 ;; esac
    [ "$#" -le 2 ] && { [ -z "$persist" ] || [ "$persist" = --default ]; } || return 2
    if [ -z "$target" ] || [ -L "$target" ] || [ ! -x "$target/bin/gradle" ] || [ ! -s "$target/lib/gradle-launcher-$requested.jar" ]; then
        printf 'Gradle %s 尚未安装或目录无效，环境未改变。\n' "$requested" >&2; return 1
    fi
    while :; do
        case "$remaining" in *:*) part="${remaining%%:*}"; remaining="${remaining#*:}"; more=1 ;; *) part="$remaining"; more=0 ;; esac
        if ! { [ -n "$old_bin" ] && [ "$part" = "$old_bin" ]; } &&
           ! { [ -n "${GRADLE_4_5_1_HOME:-}" ] && [ "$part" = "$GRADLE_4_5_1_HOME/bin" ]; } &&
           ! { [ -n "${GRADLE_6_8_HOME:-}" ] && [ "$part" = "$GRADLE_6_8_HOME/bin" ]; }; then
            cleaned="$cleaned$separator$part"; separator=:
        fi
        [ "$more" -eq 1 ] || break
    done
    if [ "$persist" = --default ]; then
        case "$GRADLE_DEFAULT_FILE" in /*) ;; *) printf '默认版本文件必须为绝对路径。\n' >&2; return 1 ;; esac
        probe="$GRADLE_DEFAULT_FILE"
        while [ "$probe" != / ]; do
            [ ! -L "$probe" ] || { printf '默认版本路径包含链接，已保留。\n' >&2; return 1; }
            probe="${probe%/*}"; [ -n "$probe" ] || probe=/
        done
        [ ! -e "$GRADLE_DEFAULT_FILE" ] || [ -f "$GRADLE_DEFAULT_FILE" ] || return 1
        if [ "$(cat "$GRADLE_DEFAULT_FILE" 2>/dev/null)" != "$requested" ]; then
            temporary="$(mktemp "$GRADLE_DEFAULT_FILE.tmp.XXXXXXXX")" || return 1
            if ! printf '%s\n' "$requested" > "$temporary" || ! mv -f -- "$temporary" "$GRADLE_DEFAULT_FILE"; then
                rm -f -- "$temporary"; return 1
            fi
        fi
    fi
    export GRADLE_HOME="$target"
    export PATH="$target/bin${separator:+:}$cleaned"
    hash -r 2>/dev/null || true
    printf '当前终端 Gradle: %s\n' "$requested"
}
if [ -f "$GRADLE_DEFAULT_FILE" ] && [ ! -L "$GRADLE_DEFAULT_FILE" ]; then
    _team_gradle_default="$(cat "$GRADLE_DEFAULT_FILE")"
    gradle_use "$_team_gradle_default" >/dev/null || return 1
    unset _team_gradle_default
fi
GRADLE_SWITCH
}
