#!/bin/bash
# 用户目录安装；不启动应用，不修改系统默认终端。
set -euo pipefail
umask 022
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/common.sh"
source "$REPO_ROOT/scripts/lib/frontend.sh"
parse_args "$@"
if "$SHOW_HELP"; then
    log "用法：install-iterm2.sh [--dry-run]；安装 iTerm2 到 ${USER_APPLICATIONS_DIR}/iTerm.app。"
    exit 0
fi
[ -z "$PROJECT_DIR" ] || die 'iTerm2 安装不接受 --project'
[ "$(uname -s)" = Darwin ] || die 'iTerm2 安装仅支持 macOS'
frontend_read_resource iterm2
EXPECTED_VERSION="$FR_VERSION"
MACOS_VERSION="$(sw_vers -productVersion)"
MACOS_MAJOR="${MACOS_VERSION%%.*}"
case "$MACOS_MAJOR" in ''|*[!0-9]*) die '无法识别 macOS 版本' ;; esac
[ "$MACOS_MAJOR" -ge 13 ] || die 'iTerm2 3.7.3 需要 macOS 13 或更新版本，未安装'
APPLICATIONS="${USER_APPLICATIONS_DIR}"
TARGET="$APPLICATIONS/iTerm.app"
frontend_check_directory "$TARGET"
if "$DRY_RUN"; then
    log "[预演] 从内网下载并校验 iTerm2 ${EXPECTED_VERSION}，安装到 ${TARGET}。"
    log '[预演] 验证应用标识、版本、可执行文件和代码签名；相同版本复用，冲突保留。'
    exit 0
fi
for tool in tar plutil codesign mktemp; do require_command "$tool"; done
validate_app() {
    local app="$1" plist="$1/Contents/Info.plist" executable identifier version
    [ -d "$app" ] && [ ! -L "$app" ] && [ -f "$plist" ] && [ ! -L "$plist" ] || return 1
    [ ! -L "$app/Contents" ] && [ ! -L "$app/Contents/MacOS" ] || return 1
    identifier="$(plutil -extract CFBundleIdentifier raw -o - "$plist" 2>/dev/null)" || return 1
    version="$(plutil -extract CFBundleShortVersionString raw -o - "$plist" 2>/dev/null)" || return 1
    executable="$(plutil -extract CFBundleExecutable raw -o - "$plist" 2>/dev/null)" || return 1
    [ "$identifier" = com.googlecode.iterm2 ] && [ "$version" = "$EXPECTED_VERSION" ] || return 1
    case "$executable" in ''|.|..|*/*|*\\*) return 1 ;; esac
    [ -f "$app/Contents/MacOS/$executable" ] && [ -x "$app/Contents/MacOS/$executable" ] && [ ! -L "$app/Contents/MacOS/$executable" ] || return 1
    codesign --verify --deep --strict "$app" || return 1
}
if [ -d "$TARGET" ]; then
    validate_app "$TARGET" || die "已有 iTerm 应用版本不符或验证失败，原应用已保留：$TARGET"
    log "复用已验证的 iTerm2 ${EXPECTED_VERSION}：$TARGET"
    exit 0
fi
frontend_fetch_resource iterm2
RECEIPT="$HOME/.local/share/team-frontend-env/receipts/iterm2-$FR_VERSION-$FR_SHA"
frontend_check_directory "$RECEIPT"
frontend_check_file "$RECEIPT/.team-frontend-env-install.json"
if [ -f "$RECEIPT/.team-frontend-env-install.json" ]; then
    [ "$(plutil -extract tool raw -o - "$RECEIPT/.team-frontend-env-install.json" 2>/dev/null)" = team-frontend-env ] &&
        [ "$(plutil -extract kind raw -o - "$RECEIPT/.team-frontend-env-install.json" 2>/dev/null)" = iterm2 ] &&
        [ "$(plutil -extract sha256 raw -o - "$RECEIPT/.team-frontend-env-install.json" 2>/dev/null)" = "$FR_SHA" ] ||
        die "已有 iTerm2 来源记录无法确认，已保留：$RECEIPT"
fi
mkdir -p -- "$APPLICATIONS"
frontend_check_directory "$TARGET"
STAGING="$(mktemp -d "$APPLICATIONS/.iterm-install.XXXXXXXX")"
trap 'rm -rf -- "$STAGING"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
tar -tf "$FR_FILE" > "$STAGING/entries" || die '无法读取 iTerm2 ZIP'
awk '
    {name=$0; sub(/\/$/, "", name); count++;
     if (name!="iTerm.app" && index(name,"iTerm.app/")!=1) exit 1;
     if (name ~ /(^|\/)\.\.?($|\/)|\\|[\r\t]/ || name ~ / -> | link to / || seen[name]++) exit 1}
    END {if(!count) exit 1}
' "$STAGING/entries" || die 'iTerm2 ZIP 包含不安全或重复路径'
tar -tvf "$FR_FILE" > "$STAGING/types" || die '无法检查 iTerm2 ZIP 类型'
awk '
    substr($0,1,1)=="-" || substr($0,1,1)=="d" {next}
    substr($0,1,1)=="l" {
        split($0,parts," -> "); if(length(parts)!=2) exit 1;
        target=parts[2]; if(target=="" || target ~ /^\/|(^|\/)\.\.($|\/)|\\|[\r\t]/) exit 1;
        next
    }
    {exit 1}
' "$STAGING/types" || die 'iTerm2 ZIP 含越界链接或特殊文件'
mkdir "$STAGING/payload"
COPYFILE_DISABLE=1 tar -xf "$FR_FILE" -C "$STAGING/payload" --no-same-owner || die 'iTerm2 ZIP 解压失败'
APP="$STAGING/payload/iTerm.app"
validate_app "$APP" || die 'iTerm2 应用标识、版本、可执行文件或代码签名校验失败'
frontend_check_directory "$TARGET"
[ ! -e "$TARGET" ] || die "安装期间出现同名应用，已保留：$TARGET"
mv -n -- "$APP" "$APPLICATIONS/"
[ ! -e "$APP" ] || die '同名 iTerm 应用已出现，未覆盖'
# 签名应用的根目录不可加入未封装文件，来源记录独立保存。
mkdir -p -- "$RECEIPT"
if [ ! -e "$RECEIPT/.team-frontend-env-install.json" ]; then
    frontend_write_marker "$RECEIPT" iterm2 "$FR_VERSION" "$FR_ARCH" "$FR_PATH" "$FR_SHA"
fi
log "iTerm2 ${EXPECTED_VERSION} 已安装：${TARGET}（未启动）"
