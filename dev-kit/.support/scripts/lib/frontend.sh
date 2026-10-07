#!/bin/bash
# 前端模块共用函数，调用者先加载 common.sh；兼容 macOS Bash 3.2。
# read/fetch 使用 FR_* 返回值，stdout 保留给日志，不通过命令替换调用。
frontend_read_resource() {
    local wanted="$1" catalog="$REPO_ROOT/config/resources.tsv" line count=0 extra
    [ -f "$catalog" ] || die '前端资源清单缺失，请向维护者获取重新发布的完整工具包'
    FR_ID=''; FR_GROUP=''; FR_VERSION=''; FR_ARCH=''; FR_PATH=''; FR_SHA=''; FR_URL=''
    line="$(awk -F '\t' -v id="$wanted" '$0 !~ /^#/ && $1==id {if (NF!=7) exit 2; print; count++} END {if(count!=1) exit 3}' "$catalog")" || die "资源缺失、重复或格式错误：$wanted"
    IFS=$'\t' read -r FR_ID FR_GROUP FR_VERSION FR_ARCH FR_PATH extra FR_SHA <<< "$line"
    [ -n "$FR_ID" ] && [ -n "$FR_VERSION" ] && [ -n "$FR_ARCH" ] && [ -n "$FR_PATH" ] && [ -n "$FR_SHA" ] || die "资源字段不完整：$wanted"
    case "$FR_GROUP" in runtime|software|plugins) ;; *) die "资源分组无效：$wanted" ;; esac
    case "$FR_ARCH" in any|arm64|x64) ;; *) die "资源架构无效：$wanted" ;; esac
    case "$FR_PATH" in /*|.|..|./*|../*|*/.|*/..|*/./*|*/../*|*/|*//*|*\\*) die "资源路径无效：$wanted" ;; esac
    [ "$FR_SHA" != - ] || die "资源缺少固定 SHA-256：$wanted"
    validate_sha256 "$FR_SHA"
    FR_SHA="$(printf '%s' "$FR_SHA" | tr 'A-F' 'a-f')"
    FR_URL="$(package_url "resources/$FR_PATH")"
}

frontend_check_directory() {
    local probe="$1"
    require_absolute_path '前端目录' "$probe"
    case "$probe/" in */../*|*/./*|*//*) die "目录路径不能包含 .、.. 或重复分隔符：$probe" ;; esac
    while :; do
        [ ! -L "$probe" ] || die "目录不能经过符号链接，原内容已保留：$probe"
        [ ! -e "$probe" ] || [ -d "$probe" ] || die "目录位置已有其他文件：$probe"
        [ "$probe" != / ] || break
        probe="$(dirname -- "$probe")"
    done
}

frontend_check_file() {
    local target="$1"
    frontend_check_directory "$(dirname -- "$target")"
    [ ! -L "$target" ] || die "文件是符号链接，原内容已保留：$target"
    [ ! -e "$target" ] || [ -f "$target" ] || die "目标不是普通文件：$target"
}

frontend_fetch_resource() {
    frontend_read_resource "$1"
    local cache="${FRONTEND_CACHE_DIR:-$HOME/Library/Caches/team-frontend-env/resources}"
    frontend_check_directory "$cache"
    FR_FILE="$cache/$FR_PATH"
    [ -f "$REPO_ROOT/scripts/prepare-resources.sh" ] || die '下载组件缺失，请使用完整工具包'
    (
        local manifest
        manifest="$(mktemp "${TMPDIR:-/tmp}/frontend-manifest.XXXXXXXX")"
        trap 'rm -f -- "$manifest"' EXIT
        trap 'exit 130' INT
        trap 'exit 143' TERM
        printf '# id\tgroup\tversion\tarch\tpath\turl\tsha256\n%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$FR_ID" "$FR_GROUP" "$FR_VERSION" "$FR_ARCH" "$FR_PATH" "$FR_URL" "$FR_SHA" > "$manifest"
        /bin/bash "$REPO_ROOT/scripts/prepare-resources.sh" --catalog "$manifest" --output "$cache" --id "$FR_ID"
    )
}

frontend_update_zsh_block() (
    label="$1" content="$2" target="${3:-${ZDOTDIR:-$HOME}/.zshrc}"
    pattern='^[a-zA-Z0-9][a-zA-Z0-9_-]*$' temporary='' block='' original='' input=/dev/null lock=''
    [[ "$label" =~ $pattern ]] || die '前端环境区块名称无效'
    frontend_check_file "$target"
    mkdir -p -- "$(dirname -- "$target")"
    lock="$target.team-frontend.lock"
    mkdir -- "$lock" 2>/dev/null || die "配置正由另一进程修改，或存在遗留锁：$lock"
    cleanup_frontend_profile() {
        [ -z "$temporary" ] || rm -f -- "$temporary"
        [ -z "$block" ] || rm -f -- "$block"
        [ -z "$original" ] || rm -f -- "$original"
        rmdir -- "$lock" 2>/dev/null || true
    }
    trap 'profile_status=$?; cleanup_frontend_profile; exit "$profile_status"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    frontend_check_file "$target"
    temporary="$(mktemp "$target.tmp.XXXXXXXX")"
    block="$(mktemp "$target.block.XXXXXXXX")"
    if [ -f "$target" ]; then
        original="$(mktemp "$target.original.XXXXXXXX")"
        cp -p -- "$target" "$original"
        cp -p -- "$target" "$temporary"
        input="$original"
    fi
    local begin="# >>> team-frontend-env $label >>>" end="# <<< team-frontend-env $label <<<"
    printf '%s\n%s\n%s\n' "$begin" "$content" "$end" > "$block"
    FRONTEND_BLOCK="$block" awk -v begin="$begin" -v end="$end" '
        function emit(    line) {while((getline line < ENVIRON["FRONTEND_BLOCK"])>0) print line; close(ENVIRON["FRONTEND_BLOCK"])}
        $0==begin {if(inside || written) {bad=1; exit}; inside=1; written=1; emit(); next}
        $0==end {if(!inside) {bad=1; exit}; inside=0; next}
        !inside {print}
        END {if(bad || inside) exit 2; if(!written) {if(NR) print ""; emit()}}
    ' "$input" > "$temporary" || die "配置受管区块重复或不完整，原文件已保留：$target"
    if [ -n "$original" ] && cmp -s "$original" "$temporary"; then
        log "前端环境配置已一致：$target"
        exit 0
    fi
    frontend_check_file "$target"
    if [ -n "$original" ]; then
        cmp -s "$original" "$target" || die "配置在处理期间已被修改，原文件已保留：$target"
        local backup="$target.team-frontend.bak"
        frontend_check_file "$backup"
        if [ ! -e "$backup" ]; then cp -p -n -- "$original" "$backup"; fi
    else
        [ ! -e "$target" ] || die "配置在处理期间已出现，已保留：$target"
    fi
    mv -f -- "$temporary" "$target"
    log "已更新前端环境配置：$target"
)

frontend_write_marker() {
    local target="$1" component="$2" version="$3" architecture="$4" archive="$5" sha="$6" field
    for field in "$component" "$version" "$architecture" "$archive" "$sha"; do
        case "$field" in ''|*[!a-zA-Z0-9._/+:-]*) die '前端安装来源标记字段无效' ;; esac
    done
    frontend_check_file "$target/.team-frontend-env-install.json"
    [ ! -e "$target/.team-frontend-env-install.json" ] || die '已有前端安装来源标记，拒绝覆盖'
    printf '{"schema":1,"tool":"team-frontend-env","kind":"%s","version":"%s","arch":"%s","archive":"%s","sha256":"%s"}\n' \
        "$component" "$version" "$architecture" "$archive" "$sha" > "$target/.team-frontend-env-install.json"
}
