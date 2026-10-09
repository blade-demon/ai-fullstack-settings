#!/bin/bash
# 固定清单资源安装到 nvm 标准目录，禁止未校验的安装脚本和源码编译。
set -euo pipefail
source "$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../lib" && pwd)/common.sh"
source "$REPO_ROOT/scripts/lib/frontend.sh"
selection=14
DRY_RUN=false
CHECK_ONLY=false
while [ "$#" -gt 0 ]; do
    case "$1" in
        --version)
            [ "$#" -ge 2 ] || die '--version 后需要 none、10、14、18、22 或 all'
            case "$2" in none|10|14|18|22|all) selection="$2" ;; *) die '--version 仅支持 none、10、14、18、22 或 all' ;; esac
            shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --check-only) CHECK_ONLY=true; shift ;;
        --help|-h)
            log '用法：install-node.sh [--version none|10|14|18|22|all] [--dry-run]'
            log '默认安装 Node 14.21.3 并设为 default；all 安装四版，保留有效 default，没有有效默认时使用 14。'
            log '指定单版本时设为 default。Apple Silicon 的 Node 10/14 使用 x64，需要已安装 Rosetta。'
            exit 0 ;;
        *) die "未知参数：$1（使用 --help 查看用法）" ;;
    esac
done
[ "$(uname -s)" = Darwin ] || die 'Node 前端环境安装目前仅支持 macOS'
case "$(uname -m)" in
    arm64|aarch64) machine_arch=arm64 ;;
    x86_64)
        machine_arch=x64
        if [ "$(sysctl -n hw.optional.arm64 2>/dev/null || true)" = 1 ]; then machine_arch=arm64; fi ;;
    *) die '不支持当前电脑架构' ;;
esac
NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
export NVM_DIR
frontend_check_directory "$NVM_DIR"
[ "$NVM_DIR" != / ] && [ "$NVM_DIR" != "$HOME" ] || die 'NVM_DIR 必须使用独立安装目录'
if [ -n "${SHELL_PROFILE:-}" ]; then nvm_profile="$SHELL_PROFILE"
elif [ "${SHELL:-/bin/zsh}" = /bin/bash ]; then nvm_profile="$HOME/.bash_profile"
else nvm_profile="${ZDOTDIR:-$HOME}/.zshrc"; fi
frontend_check_file "$nvm_profile"
frontend_check_directory "$NVM_DIR/versions/node"
frontend_check_directory "$NVM_DIR/alias"
frontend_check_file "$NVM_DIR/alias/default"
versions=(); arches=(); ids=(); candidates=(); existing=()
case "$selection" in all) majors=(10 14 18 22) ;; none) majors=() ;; *) majors=("$selection") ;; esac
for major in ${majors[@]+"${majors[@]}"}; do
    case "$major" in 10) version=10.24.1; architecture=x64 ;; 14) version=14.21.3; architecture=x64 ;; 18) version=18.20.8; architecture="$machine_arch" ;; 22) version=22.23.3; architecture="$machine_arch" ;; esac
    identifier="node$major-macos-$architecture"
    frontend_read_resource "$identifier"
    [ "$FR_VERSION" = "$version" ] && [ "$FR_ARCH" = "$architecture" ] && [ "$FR_GROUP" = runtime ] || die "Node 资源版本/架构与固定目标不匹配：$identifier"
    versions+=("$version"); arches+=("$architecture"); ids+=("$identifier")
    frontend_check_directory "$NVM_DIR/versions/node/v$version"
    if "$DRY_RUN"; then log "[预演] 固定 SHA-256 校验 $FR_URL → $NVM_DIR/versions/node/v$version"; fi
done
frontend_read_resource nvm
[ "$FR_VERSION" = 0.40.8 ] && [ "$FR_ARCH" = any ] && [ "$FR_GROUP" = runtime ] || die 'nvm 资源必须为固定的 0.40.8 通用版本'
if "$DRY_RUN"; then
    log "[预演] 复用有效 nvm 或安装固定资源：$FR_URL → $NVM_DIR"
    if [ "$machine_arch" = arm64 ] && { [ "$selection" = all ] || [ "$selection" = 14 ] || [ "$selection" = 10 ]; }; then
        log '[预演] Node 10/14 需要 Rosetta；正式安装前先确认 x64 程序可执行，不自动安装 Rosetta。'
    fi
    log "[预演] 验证 nvm ls/use 和 Node 版本；备份并更新 ${nvm_profile} 的 nvm 受管区块。"
    log '[预演] 不执行 SDK、不联网、不写文件。'
    exit 0
fi
if [ "$machine_arch" = arm64 ] && { [ "$selection" = all ] || [ "$selection" = 14 ] || [ "$selection" = 10 ]; }; then
    arch -x86_64 /usr/bin/true 2>/dev/null || die 'Node 10/14 仅提供 x64 macOS 二进制；请先由你或管理员安装 Rosetta 2，再重试。也可先选择原生 Node 18 或 22。'
fi
for command in tar awk shasum mktemp; do require_command "$command"; done
work=''; lock=''
cleanup_node() {
    [ -z "$work" ] || rm -rf -- "$work"
    [ -z "$lock" ] || rmdir -- "$lock" 2>/dev/null || true
    return 0
}
trap 'node_status=$?; cleanup_node; exit "$node_status"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

nvm_version() (
    # nvm 支持的调用环境不包含 nounset；限制在子 shell 内，避免改变安装器选项。
    set +u
    export NVM_DIR="$1"
    . "$NVM_DIR/nvm.sh" --no-use || exit 1
    type nvm >/dev/null 2>&1 || exit 1
    nvm --version
)
verify_node() {
    local root="$1" wanted="$2" actual
    [ -f "$root/bin/node" ] && [ -x "$root/bin/node" ] && [ ! -L "$root/bin/node" ] || die "Node 目录不完整，已保留：$root"
    actual="$("$root/bin/node" --version)" || die "Node $wanted 无法运行：$root"
    [ "$actual" = "v$wanted" ] || die "Node 版本不匹配：期望 v${wanted}，实际 ${actual}；原目录已保留"
    [ -f "$root/lib/node_modules/npm/bin/npm-cli.js" ] && [ -e "$root/bin/npm" ] || die "Node $wanted 缺少 npm，原目录已保留"
}
verify_nvm_node() (
    set +u
    export NVM_DIR="$1"
    local version="$2"
    . "$NVM_DIR/nvm.sh" --no-use || exit 1
    nvm ls "v$version" >/dev/null || exit 1
    nvm use --silent "v$version" || exit 1
    [ "$(command -v node)" = "$NVM_DIR/versions/node/v$version/bin/node" ] || exit 1
    [ "$(node --version)" = "v$version" ]
)

fresh_nvm=true
if [ -e "$NVM_DIR" ]; then
    [ -f "$NVM_DIR/nvm.sh" ] && [ ! -L "$NVM_DIR/nvm.sh" ] || die "已有 nvm 目录未知或不完整，不会覆盖：$NVM_DIR"
    installed_nvm="$(nvm_version "$NVM_DIR")" || die "已有 nvm 无法正常加载，不会覆盖：$NVM_DIR"
    [ -n "$installed_nvm" ] || die '已有 nvm 返回空版本，原目录已保留'
    log "复用已有 nvm ${installed_nvm}：$NVM_DIR"
    fresh_nvm=false
fi
for ((i=0; i<${#versions[@]}; i++)); do
    target="$NVM_DIR/versions/node/v${versions[$i]}"
    if [ -e "$target" ]; then
        verify_node "$target" "${versions[$i]}"
        verify_nvm_node "$NVM_DIR" "${versions[$i]}" || die "已有 Node 无法由 nvm 切换，已保留：$target"
        existing+=(true)
    else existing+=(false); fi
done
frontend_node_default_plan "$selection" verify
planned_default_before="$FRONTEND_DEFAULT_BEFORE"
planned_default_after="$FRONTEND_DEFAULT_AFTER"
if "$CHECK_ONLY"; then log 'nvm/Node 预检通过，未执行安装。'; exit 0; fi
mkdir -p -- "$(dirname -- "$NVM_DIR")"
frontend_check_directory "$(dirname -- "$NVM_DIR")"
lock_candidate="$NVM_DIR.team-frontend.lock"
mkdir -- "$lock_candidate" 2>/dev/null || die "Node 安装正在进行或存在遗留锁：$lock_candidate"
lock="$lock_candidate"
work="$(mktemp -d "$(dirname -- "$NVM_DIR")/.frontend-node.XXXXXXXX")"
mkdir "$work/staged"
staged_nvm="$work/staged/nvm"
mkdir "$staged_nvm"

# 校验全量路径，Node 只允许官方 npm/npx/corepack 三个已知内部链接。
check_archive() {
    local archive="$1" root="$2" kind="$3"
    tar -tf "$archive" > "$work/entries" || die '无法读取归档'
    awk -v root="$root" '
        {count++; if ($0!=root && index($0,root "/")!=1) bad=1;
         if ($0 ~ /(^|\/)\.\.(\/|$)/ || $0 ~ /^\// || $0 ~ /\\/ || $0 ~ /[[:cntrl:]]/) bad=1}
        END {exit (bad || !count)}
    ' "$work/entries" || die '归档包含越界路径或错误根目录'
    tar -tvf "$archive" > "$work/types" || die '无法读取归档文件类型'
    if [ "$kind" = node ]; then
        awk -v root="$root" '
            substr($0,1,1)=="d" || substr($0,1,1)=="-" {next}
            substr($0,1,1)=="l" {
                if (index($0,root "/bin/npm -> ../lib/node_modules/npm/bin/npm-cli.js") && $NF=="../lib/node_modules/npm/bin/npm-cli.js") next
                if (index($0,root "/bin/npx -> ../lib/node_modules/npm/bin/npx-cli.js") && $NF=="../lib/node_modules/npm/bin/npx-cli.js") next
                if (index($0,root "/bin/corepack -> ../lib/node_modules/corepack/dist/corepack.js") && $NF=="../lib/node_modules/corepack/dist/corepack.js") next
            }
            {exit 1}
        ' "$work/types" || die 'Node 归档含有非官方链接或特殊文件'
    else
        # nvm 的测试目录可能包含链接，仅提取这三个已检查为普通文件的入口。
        local member
        for member in nvm.sh nvm-exec bash_completion; do
            [ "$(awk -v entry="$root/$member" '$0==entry {n++} END {print n+0}' "$work/entries")" = 1 ] || die "nvm 归档入口缺失或重复：$member"
            tar -tvf "$archive" "$root/$member" | awk 'substr($0,1,1)!="-" {exit 1}' || die "nvm 入口不是普通文件：$member"
        done
    fi
}

if "$fresh_nvm"; then
    frontend_fetch_resource nvm
    check_archive "$FR_FILE" nvm-0.40.8 nvm
    mkdir "$work/nvm-payload"
    tar -xf "$FR_FILE" -C "$work/nvm-payload" --no-same-owner nvm-0.40.8/nvm.sh nvm-0.40.8/nvm-exec nvm-0.40.8/bash_completion
    cp -p "$work/nvm-payload/nvm-0.40.8/nvm.sh" "$work/nvm-payload/nvm-0.40.8/nvm-exec" "$work/nvm-payload/nvm-0.40.8/bash_completion" "$staged_nvm/"
    [ "$(nvm_version "$staged_nvm")" = 0.40.8 ] || die 'nvm 版本验证失败，未安装'
    frontend_write_marker "$staged_nvm" nvm "$FR_VERSION" "$FR_ARCH" "$FR_PATH" "$FR_SHA"
else
    # 只复制加载入口到隔离验证目录，不改变已有 nvm。
    cp -p "$NVM_DIR/nvm.sh" "$staged_nvm/nvm.sh"
fi
mkdir -p "$staged_nvm/versions/node"
for ((i=0; i<${#versions[@]}; i++)); do
    if "${existing[$i]}"; then candidates+=(""); continue; fi
    version="${versions[$i]}"; architecture="${arches[$i]}"
    frontend_fetch_resource "${ids[$i]}"
    root="node-v$version-darwin-$architecture"
    check_archive "$FR_FILE" "$root" node
    mkdir "$work/payload-$i"
    tar -xf "$FR_FILE" -C "$work/payload-$i" --no-same-owner || die "Node $version 解压失败"
    candidate="$work/payload-$i/$root"
    verify_node "$candidate" "$version"
    frontend_write_marker "$candidate" node "$version" "$architecture" "$FR_PATH" "$FR_SHA"
    mv -- "$candidate" "$staged_nvm/versions/node/v$version"
    verify_nvm_node "$staged_nvm" "$version" || die "Node $version 无法使用 nvm ls/use，未发布安装"
    candidates+=("$staged_nvm/versions/node/v$version")
done
# 所有目标完成下载、结构及执行验证后才发布，避免 all 因缺包/坏包产生半套安装。
if "$fresh_nvm"; then
    publish="$work/staged/${NVM_DIR##*/}"
    if [ "$publish" != "$staged_nvm" ]; then mv -- "$staged_nvm" "$publish"; fi
    [ ! -e "$NVM_DIR" ] && [ ! -L "$NVM_DIR" ] || die '安装期间 nvm 目录已出现，已保留原内容'
    mv -n -- "$publish" "$(dirname -- "$NVM_DIR")/"
    [ ! -e "$publish" ] || die '安装期间 nvm 目录已出现，已保留原内容'
else
    frontend_check_directory "$NVM_DIR/versions/node"
    mkdir -p "$NVM_DIR/versions/node"
    for ((i=0; i<${#versions[@]}; i++)); do
        "${existing[$i]}" && continue
        target="$NVM_DIR/versions/node/v${versions[$i]}"
        [ ! -e "$target" ] && [ ! -L "$target" ] || die '安装期间 Node 目标已出现，已保留原内容'
        mv -n -- "${candidates[$i]}" "$NVM_DIR/versions/node/"
        [ ! -e "${candidates[$i]}" ] || die '安装期间 Node 目标已出现，已保留原内容'
    done
fi
for version in ${versions[@]+"${versions[@]}"}; do
    verify_nvm_node "$NVM_DIR" "$version" || die "安装后 nvm 切换 Node $version 验证失败"
    log "已验证 Node ${version}：nvm use $version"
done
frontend_check_directory "$NVM_DIR/alias"
frontend_check_file "$NVM_DIR/alias/default"
FRONTEND_DEFAULT_BEFORE="$planned_default_before"
FRONTEND_DEFAULT_AFTER="$planned_default_after"
if [ "$selection" = none ]; then
    log "本次仅安装 nvm，保留已有 Node 与默认别名。"
elif [ "$FRONTEND_DEFAULT_BEFORE" != "$FRONTEND_DEFAULT_AFTER" ]; then
    (
        set +u
        . "$NVM_DIR/nvm.sh" --no-use
        nvm alias default "$FRONTEND_DEFAULT_AFTER" >/dev/null
    ) || die '无法保存 nvm default'
    [ "$(cat "$NVM_DIR/alias/default")" = "$FRONTEND_DEFAULT_AFTER" ] || die 'nvm default 保存验证失败'
fi
if [ "$selection" != none ]; then
    frontend_node_default_plan all verify
    [ "$FRONTEND_DEFAULT_VALIDATION" = valid ] || die 'nvm default 解析或运行验证失败'
    log "已验证有效 nvm default：${FRONTEND_DEFAULT_BEFORE}；nvm use default 与 Node 加载验证通过。"
fi
body="$(printf 'export NVM_DIR=%s\n[ ! -s "$NVM_DIR/nvm.sh" ] || . "$NVM_DIR/nvm.sh"\n' "$(shell_quote "$NVM_DIR")")"
frontend_update_zsh_block nvm "$body" "$nvm_profile"
log 'nvm 环境已验证。新开终端生效；当前终端可先执行：'
printf 'export NVM_DIR=%s\n. "$NVM_DIR/nvm.sh"\n' "$(shell_quote "$NVM_DIR")"
log '查看版本：nvm ls'
for version in ${versions[@]+"${versions[@]}"}; do log "当前终端切换：nvm use $version"; done
if [ "$selection" != none ]; then
    log '新终端默认：nvm alias default <已安装版本>；当前终端应用默认：nvm use default'
    log '验证：node -v；npm -v'
else log '本次未安装 Node；既有版本和默认值以 nvm ls 为准。'; fi
