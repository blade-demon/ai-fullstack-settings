#!/bin/bash
# 固定快照安装，不运行上游安装器，不更改登录 Shell。
set -euo pipefail
umask 022
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/common.sh"
source "$REPO_ROOT/scripts/lib/frontend.sh"
DRY_RUN=false
WITH_PLUGINS=true
CHECK_ONLY=false
while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=true ;;
        --check-only) CHECK_ONLY=true ;;
        --without-plugins) WITH_PLUGINS=false ;;
        --help|-h) log '用法：install-zsh.sh [--dry-run] [--without-plugins]；保留用户主题、配置和已有插件。'; exit 0 ;;
        *) die "未知参数：$1" ;;
    esac
    shift
done
[ "$(uname -s)" = Darwin ] || die '终端环境安装仅支持 macOS'
ZSH_ROOT="${ZSH:-$HOME/.oh-my-zsh}"
CUSTOM_ROOT="${ZSH_CUSTOM:-$ZSH_ROOT/custom}"
PROFILE="${ZDOTDIR:-$HOME}/.zshrc"
frontend_check_directory "$ZSH_ROOT"
frontend_check_directory "$CUSTOM_ROOT"
frontend_check_file "$PROFILE"
frontend_read_resource oh-my-zsh
if "$WITH_PLUGINS"; then
    frontend_read_resource zsh-autosuggestions
    frontend_read_resource zsh-syntax-highlighting
fi
if "$DRY_RUN"; then
    log "[预演] 验证并安装 Oh My Zsh 固定快照到 ${ZSH_ROOT}。"
    log '[预演] Oh My Zsh 框架需要可用 Git；系统 Git 需已安装 Command Line Tools（CLT）。本次不执行 Git。'
    if "$WITH_PLUGINS"; then
        log '[预演] 配置 git、z、zsh-autosuggestions、zsh-syntax-highlighting，语法高亮最后加载。'
    fi
    log "[预演] 备份后幂等更新 $PROFILE 的独立区块；不运行官方 install.sh、不更改登录 Shell。"
    exit 0
fi
check_git_dependency() {
    local git_path link parent hops=0 developer version
    git_path="$(type -P git || true)"
    [ -n "$git_path" ] || die 'Oh My Zsh 框架需要可用 Git，请先安装 Git 或 Command Line Tools（CLT）后重试'
    # Homebrew 等安装常使用链接；识别最终是否指向系统占位程序后才允许执行。
    while :; do
        parent="$(CDPATH= cd -- "$(dirname -- "$git_path")" && pwd -P)" || die '无法确认 Git 路径'
        git_path="$parent/$(basename -- "$git_path")"
        [ -L "$git_path" ] || break
        hops=$((hops + 1))
        [ "$hops" -le 32 ] || die 'Git 路径包含循环或过多符号链接'
        link="$(readlink "$git_path")" || die '无法读取 Git 链接'
        case "$link" in /*) git_path="$link" ;; *) git_path="$parent/$link" ;; esac
    done
    [ -f "$git_path" ] && [ -x "$git_path" ] || die 'Git 不是可执行程序，请先安装可用 Git'
    if [ "$git_path" = /usr/bin/git ]; then
        developer="$(xcode-select -p 2>/dev/null)" || developer=''
        case "$developer" in /*) ;; *) developer='' ;; esac
        [ -n "$developer" ] && [ "$developer" != / ] && [ -d "$developer" ] &&
            [ -x "$developer/usr/bin/git" ] ||
            die '检测到系统 Git 占位程序，但没有有效 Command Line Tools（CLT）；请先安装 Git 或 CLT 后重试，本工具不会触发系统安装'
    fi
    version="$("$git_path" --version 2>/dev/null)" || die 'Git 版本验证失败，请先修复 Git 或 CLT'
    [[ "$version" =~ ^git[[:space:]]version[[:space:]][0-9]+\. ]] || die 'Git 版本输出无效，请先安装可用 Git'
    log "已验证 Git 依赖：$version"
}
# 固定上游快照即使不启用插件，也会用 git rev-parse HEAD 生成补全缓存元数据。
check_git_dependency
for tool in tar awk mktemp zsh; do require_command "$tool"; done
valid_framework() {
    local directory="$1" item
    for item in oh-my-zsh.sh lib/completion.zsh plugins/git/git.plugin.zsh plugins/z/z.plugin.zsh; do
        [ -f "$directory/$item" ] && [ ! -L "$directory/$item" ] || return 1
    done
    frontend_check_directory "$directory/lib"
    frontend_check_directory "$directory/plugins/git"
    frontend_check_directory "$directory/plugins/z"
}
if [ -e "$ZSH_ROOT" ]; then
    valid_framework "$ZSH_ROOT" || die "已有 Oh My Zsh 目录无法确认，原文件已保留：$ZSH_ROOT"
fi
if "$CHECK_ONLY"; then log 'Oh My Zsh 预检通过，未执行安装。'; exit 0; fi
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/team-zsh.XXXXXXXX")"
WORK_DIR="$(CDPATH= cd -- "$WORK_DIR" && pwd -P)"
PUBLISH=''
trap 'rm -rf -- "$WORK_DIR"; [ -z "$PUBLISH" ] || rm -rf -- "$PUBLISH"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# 上游文档包含 ../../docs 链接。先静态验证所有名称和链接；不允许链接作为
# 任何成员或链接目标的祖先，避免先链接再写入和链接链的路径归一化绕过。
extract_snapshot() {
    local archive="$1" destination="$2" root
    mkdir "$destination"
    tar -tf "$archive" > "$WORK_DIR/entries" || die '无法读取终端工具归档'
    root="$(awk 'NR==1 {split($0,p,"/"); print p[1]}' "$WORK_DIR/entries")"
    [ -n "$root" ] || die '终端工具归档为空'
    awk -v root="$root" '
        {name=$0; sub(/\/$/,"",name); count++;
         if(name!=root && index(name,root "/")!=1) exit 1;
         if(name ~ /^\/|(^|\/)\.\.?($|\/)|\\|[\r\t]/ || name ~ / -> | link to / || seen[name]++) exit 1}
        END {if(!count) exit 1}
    ' "$WORK_DIR/entries" || die '终端工具归档含越界、重复或无效路径'
    tar -tvf "$archive" > "$WORK_DIR/types" || die '无法检查终端工具归档类型'
    awk -v root="$root" '
        FNR==NR {name=$0; sub(/\/$/,"",name); members[name]=1; next}
        {
            kind=substr($0,1,1); if(kind=="-" || kind=="d") next;
            if(kind!="l") {bad=1; next}
            start=index($0,root "/"); if(!start) {bad=1; next}
            line=substr($0,start); n=split(line,p," -> ");
            if(n!=2 || !members[p[1]] || p[2]=="" || p[2] ~ /^\/|\\|[\r\t]/) {bad=1; next}
            links[p[1]]=p[2]
        }
        END {
            if(bad) exit 1;
            for(name in members) {parent=name; while(sub(/\/[^\/]+$/,"",parent)) if(parent in links) exit 1}
            for(name in links) {
                base=name; sub(/\/[^\/]+$/,"",base); n=split(base "/" links[name],parts,"/"); depth=0; result="";
                for(i=1;i<=n;i++) {
                    if(parts[i]=="" || parts[i]==".") continue;
                    if(parts[i]=="..") {if(depth<=1) exit 1; delete stack[depth--]}
                    else stack[++depth]=parts[i];
                    result=stack[1]; for(j=2;j<=depth;j++) result=result "/" stack[j];
                    if(result in links) exit 1;
                }
                if(stack[1]!=root) exit 1;
            }
        }
    ' "$WORK_DIR/entries" "$WORK_DIR/types" || die '终端工具归档含越界链接、链接链或特殊文件'
    COPYFILE_DISABLE=1 tar -xf "$archive" -C "$destination" --no-same-owner || die '终端工具归档解压失败'
    SNAPSHOT="$destination/$root"
}
publish_snapshot() {
    local source="$1" target="$2" component="$3" parent
    parent="$(dirname -- "$target")"
    frontend_check_directory "$target"
    [ ! -e "$target" ] || die "安装期间出现同名目录，已保留：$target"
    mkdir -p -- "$parent"
    PUBLISH="$(mktemp -d "$parent/.terminal-install.XXXXXXXX")"
    mv -- "$source" "$PUBLISH/$(basename -- "$target")"
    source="$PUBLISH/$(basename -- "$target")"
    frontend_write_marker "$source" "$component" "$FR_VERSION" "$FR_ARCH" "$FR_PATH" "$FR_SHA"
    frontend_check_directory "$target"
    [ ! -e "$target" ] || die "安装期间出现同名目录，已保留：$target"
    mv -n -- "$source" "$parent/"
    [ ! -e "$source" ] || die "同名目录已出现，未覆盖：$target"
    rmdir -- "$PUBLISH"
    PUBLISH=''
}
if [ ! -e "$ZSH_ROOT" ]; then
    frontend_fetch_resource oh-my-zsh
    extract_snapshot "$FR_FILE" "$WORK_DIR/oh-my-zsh"
    valid_framework "$SNAPSHOT" || die 'Oh My Zsh 归档缺少框架和内置插件'
    publish_snapshot "$SNAPSHOT" "$ZSH_ROOT" oh-my-zsh
else
    log "复用已有 Oh My Zsh，保留 custom 内容：$ZSH_ROOT"
fi
mkdir -p -- "$CUSTOM_ROOT"
if "$WITH_PLUGINS"; then
    for plugin in zsh-autosuggestions zsh-syntax-highlighting; do
        target="$CUSTOM_ROOT/plugins/$plugin"
        frontend_check_directory "$target"
        if [ -e "$target" ]; then
            [ -f "$target/$plugin.plugin.zsh" ] && [ ! -L "$target/$plugin.plugin.zsh" ] || die "已有插件目录无法确认，已保留：$target"
            log "复用已有插件：$target"
        else
            frontend_fetch_resource "$plugin"
            extract_snapshot "$FR_FILE" "$WORK_DIR/$plugin"
            [ -f "$SNAPSHOT/$plugin.plugin.zsh" ] && [ ! -L "$SNAPSHOT/$plugin.plugin.zsh" ] || die "插件归档缺少入口：$plugin"
            publish_snapshot "$SNAPSHOT" "$target" "$plugin"
        fi
    done
fi
quoted_zsh="$(shell_quote "$ZSH_ROOT")"
quoted_custom="$(shell_quote "$CUSTOM_ROOT")"
managed_framework=false
marker="$ZSH_ROOT/.team-frontend-env-install.json"
if [ -f "$marker" ] && [ ! -L "$marker" ] &&
    [ "$(plutil -extract schema raw -o - "$marker" 2>/dev/null)" = 1 ] &&
    [ "$(plutil -extract tool raw -o - "$marker" 2>/dev/null)" = team-frontend-env ] &&
    [ "$(plutil -extract kind raw -o - "$marker" 2>/dev/null)" = oh-my-zsh ]; then
    managed_framework=true
fi
# 使用单引号引用默认路径，以支持空格、美元符号和单引号等用户目录名称。
content='# 保留用户主题、plugins 和外部框架的更新政策。'
if "$managed_framework"; then content="$content
zstyle ':omz:update' mode disabled"; fi
content="$content
$(printf '%s\n' \
    "[[ -n \${ZSH-} ]] || export ZSH=$quoted_zsh" "[[ -n \${ZSH_CUSTOM-} ]] || ZSH_CUSTOM=$quoted_custom" \
    'typeset -ga plugins' 'if (( ! ${+functions[omz]} )); then')"
if "$WITH_PLUGINS"; then
    content="$content
  for _team_plugin in git z; do
    (( \${plugins[(Ie)\$_team_plugin]} )) || plugins+=(\"\$_team_plugin\")
  done
  # 外部插件稍后单独补充，兼容用户在 .zshrc 中另设 ZSH_CUSTOM。
  plugins=(\"\${(@)plugins:#zsh-autosuggestions}\")
  plugins=(\"\${(@)plugins:#zsh-syntax-highlighting}\")"
fi
content="$content
  source \"\$ZSH/oh-my-zsh.sh\"
fi"
if "$WITH_PLUGINS"; then
    content="$content
for _team_plugin in git z zsh-autosuggestions zsh-syntax-highlighting; do
  if (( ! \${plugins[(Ie)\$_team_plugin]} )); then
    case \$_team_plugin in
      git|z) source $quoted_zsh/plugins/\$_team_plugin/\$_team_plugin.plugin.zsh ;;
      *)
        if [[ -f \"\$ZSH_CUSTOM/plugins/\$_team_plugin/\$_team_plugin.plugin.zsh\" ]]; then
          source \"\$ZSH_CUSTOM/plugins/\$_team_plugin/\$_team_plugin.plugin.zsh\"
        else
          source $quoted_custom/plugins/\$_team_plugin/\$_team_plugin.plugin.zsh
        fi ;;
    esac
    plugins+=(\"\$_team_plugin\")
  fi
done
plugins=(\"\${(@)plugins:#zsh-syntax-highlighting}\" zsh-syntax-highlighting)"
fi
content="$content
unset _team_plugin"
frontend_update_zsh_block terminal-tools "$content" "$PROFILE"
log 'Oh My Zsh 配置完成；新开终端生效，登录 Shell 和用户主题保持原样。'
