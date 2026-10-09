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

# 展示只静态读取；真实安装用 nvm 解析、切换并运行目标。两个入口共用默认规则。
_frontend_nvm_default_version() (
    set +u
    local target actual
    . "$NVM_DIR/nvm.sh" --no-use >/dev/null 2>&1 || exit 1
    target="$(nvm version default)" || exit 1
    [ -n "$target" ] && [ "$target" != N/A ] && [ "$target" != none ] || exit 1
    nvm use --silent default >/dev/null 2>&1 || exit 1
    actual="$(node --version)" || exit 1
    if [ "$target" = system ]; then
        [[ "$actual" =~ ^v[0-9]+\.[0-9]+\.[0-9]+ ]] || exit 1
    else [ "$actual" = "$target" ] || exit 1; fi
    printf '%s' "$actual"
)
frontend_node_default_plan() {
    local selection="$1" mode="${2:-static}" current='' resolved='' major='' depth=0
    FRONTEND_DEFAULT_BEFORE=''; FRONTEND_DEFAULT_AFTER=''; FRONTEND_DEFAULT_VALIDATION=missing
    if [ -f "$NVM_DIR/alias/default" ] && [ ! -L "$NVM_DIR/alias/default" ]; then
        current="$(cat "$NVM_DIR/alias/default")"
        FRONTEND_DEFAULT_BEFORE="$current"
        FRONTEND_DEFAULT_VALIDATION=pending
    fi
    if [ "$selection" = none ]; then
        FRONTEND_DEFAULT_AFTER="$current"
        FRONTEND_DEFAULT_IMPACT="默认保持 ${current:-未设置}；仅安装 nvm，不要求已有 Node"
        return 0
    fi
    if [ -n "$current" ]; then
        if [ "$mode" = verify ]; then
            resolved="$(_frontend_nvm_default_version)" && FRONTEND_DEFAULT_VALIDATION=valid || FRONTEND_DEFAULT_VALIDATION=invalid
        else
            resolved="$current"
            while [ -f "$NVM_DIR/alias/$resolved" ] && [ ! -L "$NVM_DIR/alias/$resolved" ] && [ "$depth" -lt 20 ]; do
                resolved="$(cat "$NVM_DIR/alias/$resolved")"; depth=$((depth + 1))
            done
            case "$resolved" in
                v[0-9]*.[0-9]*.[0-9]*)
                    [ -x "$NVM_DIR/versions/node/$resolved/bin/node" ] || FRONTEND_DEFAULT_VALIDATION=invalid ;;
                system) command -v node >/dev/null 2>&1 || FRONTEND_DEFAULT_VALIDATION=invalid ;;
            esac
            [ "$depth" -lt 20 ] || FRONTEND_DEFAULT_VALIDATION=invalid
        fi
    fi
    case "$selection" in
        all)
            if [ "$FRONTEND_DEFAULT_VALIDATION" = valid ] || [ "$FRONTEND_DEFAULT_VALIDATION" = pending ]; then
                FRONTEND_DEFAULT_AFTER="$current"
                FRONTEND_DEFAULT_IMPACT="默认保留 ${current}（执行前验证，失效则恢复 v14.21.3）"
            else
                FRONTEND_DEFAULT_AFTER=v14.21.3
                if [ -n "$current" ]; then FRONTEND_DEFAULT_IMPACT="默认 $current 已失效 → v14.21.3"
                else FRONTEND_DEFAULT_IMPACT='新终端默认 未设置 → v14.21.3'; fi
            fi ;;
        10) FRONTEND_DEFAULT_AFTER=v10.24.1 ;;
        14) FRONTEND_DEFAULT_AFTER=v14.21.3 ;;
        18) FRONTEND_DEFAULT_AFTER=v18.20.8 ;;
        22) FRONTEND_DEFAULT_AFTER=v22.23.3 ;;
    esac
    if [ "$selection" != all ]; then FRONTEND_DEFAULT_IMPACT="新终端默认 ${current:-未设置} → $FRONTEND_DEFAULT_AFTER"; fi
    return 0
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
    local profile extra_key extra_value
    case "$component" in
        nvm|node)
            profile="${nvm_profile:-${SHELL_PROFILE:-${ZDOTDIR:-$HOME}/.zshrc}}"
            extra_key=nvm_dir; extra_value="${NVM_DIR:-$HOME/.nvm}" ;;
        *) profile="${PROFILE:-${ZDOTDIR:-$HOME}/.zshrc}"; extra_key=zsh_custom; extra_value="${CUSTOM_ROOT:-${ZSH_CUSTOM:-${ZSH:-$HOME/.oh-my-zsh}/custom}}" ;;
    esac
    {
        printf '{"schema":1,"tool":"team-frontend-env","kind":"%s","version":"%s","arch":"%s","archive":"%s","sha256":"%s","profile":' \
            "$component" "$version" "$architecture" "$archive" "$sha"
        json_quote "$profile"
        printf ',"%s":' "$extra_key"; json_quote "$extra_value"
        case "$component" in
            nvm|oh-my-zsh|zsh-autosuggestions|zsh-syntax-highlighting)
                local file relative digest separator=''
                printf ',"files":{'
                while IFS= read -r -d '' file; do
                    relative="${file#"$target/"}"
                    [ "$relative" != .team-frontend-env-install.json ] || continue
                    digest="$(shasum -a 256 < "$file")" || return 1
                    printf '%s' "$separator"; json_quote "$relative"; printf ':'; json_quote "${digest%% *}"
                    separator=,
                done < <(find "$target" -type f -print0)
                printf '},"links":{'; separator=''
                while IFS= read -r -d '' file; do
                    relative="${file#"$target/"}"
                    printf '%s' "$separator"; json_quote "$relative"; printf ':'; json_quote "$(readlink "$file")"
                    separator=,
                done < <(find "$target" -type l -print0)
                printf '},"directories":['; separator=''
                while IFS= read -r -d '' file; do
                    [ "$file" != "$target" ] || continue
                    printf '%s' "$separator"; json_quote "${file#"$target/"}"; separator=,
                done < <(find "$target" -type d -print0)
                printf ']' ;;
        esac
        printf '}\n'
    } > "$target/.team-frontend-env-install.json"
}
