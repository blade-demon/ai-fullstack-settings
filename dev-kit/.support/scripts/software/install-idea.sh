#!/bin/bash
# 只安装到当前用户的 Applications；不提权、不启动 IDEA、不覆盖已有应用。
set -euo pipefail
umask 022
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/common.sh"

DMG=''
EXPECTED_SHA=''
EXPECTED_VERSION=''
DRY_RUN=false
while [ "$#" -gt 0 ]; do
    case "$1" in
        --dmg|--sha256|--version)
            [ "$#" -ge 2 ] && [ -n "$2" ] || die "$1 后需要非空值"
            case "$2" in --*) die "$1 后需要非空值" ;; esac
            case "$1" in
                --dmg) DMG="$2" ;;
                --sha256) EXPECTED_SHA="$2" ;;
                --version) EXPECTED_VERSION="$2" ;;
            esac
            shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --help|-h)
            log '用法：install-idea.sh --dmg 文件 --sha256 摘要 --version 版本 [--dry-run]'
            log '校验并安装到 ~/Applications/IntelliJ IDEA CE.app；不会覆盖其他版本，不会打开 IDEA。'
            exit 0 ;;
        *) die "未知参数：$1" ;;
    esac
done
[ -n "$DMG" ] && [ -n "$EXPECTED_SHA" ] && [ -n "$EXPECTED_VERSION" ] || die '必须提供 --dmg、--sha256 和 --version'
validate_sha256 "$EXPECTED_SHA"
[ -f "$DMG" ] || die "找不到 DMG 文件：$DMG"
[ -d "$HOME" ] || die "用户目录不存在：$HOME"
USER_HOME="$(CDPATH= cd -- "$HOME" && pwd -P)"
APPLICATIONS="$USER_HOME/Applications"
APP_NAME='IntelliJ IDEA CE.app'
TARGET="$APPLICATIONS/$APP_NAME"

check_destination() {
    [ ! -L "$APPLICATIONS" ] || die "用户 Applications 是符号链接，不能安装；原目录已保留：$APPLICATIONS"
    if [ -e "$APPLICATIONS" ] && [ ! -d "$APPLICATIONS" ]; then
        die "用户 Applications 不是目录，原文件已保留：$APPLICATIONS"
    fi
    [ ! -L "$TARGET" ] || die "已有 IDEA 是符号链接，原目标已保留：$TARGET"
    if [ -e "$TARGET" ] && [ ! -d "$TARGET" ]; then
        die "已有 IDEA 目标不是应用目录，原文件已保留：$TARGET"
    fi
}
check_destination
if "$DRY_RUN"; then
    log "[预演] 校验 DMG SHA-256：$DMG"
    log "[预演] 只读挂载并验证 IDEA 社区版 ${EXPECTED_VERSION}。"
    log "[预演] 用户安装位置：$TARGET"
    log '[预演] 相同版本和构建号会复用；其他已有应用会保留并报错。本次不挂载、不复制。'
    exit 0
fi

for tool in shasum hdiutil ditto plutil mktemp mv; do require_command "$tool"; done
ACTUAL_SHA="$(shasum -a 256 < "$DMG")" || die '无法计算 DMG 的 SHA-256'
ACTUAL_SHA="${ACTUAL_SHA%% *}"
EXPECTED_SHA="$(printf '%s' "$EXPECTED_SHA" | tr 'A-F' 'a-f')"
[ "$ACTUAL_SHA" = "$EXPECTED_SHA" ] || die 'IDEA DMG 的 SHA-256 校验失败；未挂载或安装。'
DMG="$(CDPATH= cd -- "$(dirname -- "$DMG")" && pwd -P)/$(basename -- "$DMG")"

MOUNT_ROOT=''
MOUNT_POINT=''
MOUNT_ATTEMPTED=false
STAGING=''
SUCCESS_MESSAGE=''
cleanup() {
    status=$?
    trap - EXIT
    set +e
    detached=true
    if "$MOUNT_ATTEMPTED"; then
        if ! hdiutil detach "$MOUNT_POINT"; then
            detached=false
            printf '错误：无法卸载本次挂载的 DMG，挂载目录已保留，请关闭使用该卷的程序后手动卸载：%s\n' "$MOUNT_POINT" >&2
            [ "$status" -ne 0 ] || status=1
        fi
    fi
    if [ -n "$STAGING" ]; then
        rm -rf -- "$STAGING" || { printf '错误：临时安装目录未清理：%s\n' "$STAGING" >&2; status=1; }
    fi
    # 只有确认卸载成功后才递归删除挂载临时目录，绝不清理仍挂载的卷。
    if "$detached" && [ -n "$MOUNT_ROOT" ]; then
        rm -rf -- "$MOUNT_ROOT" || { printf '错误：临时挂载目录未清理：%s\n' "$MOUNT_ROOT" >&2; status=1; }
    fi
    if [ "$status" -eq 0 ] && [ -n "$SUCCESS_MESSAGE" ]; then log "$SUCCESS_MESSAGE"; fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# 输出构建号供源应用、暂存副本与已有应用之间比较。
bundle_build() {
    local app="$1" plist identifier version build executable
    [ -d "$app" ] && [ ! -L "$app" ] || return 1
    plist="$app/Contents/Info.plist"
    [ -f "$plist" ] && [ ! -L "$plist" ] || return 1
    identifier="$(plutil -extract CFBundleIdentifier raw -o - "$plist" 2>/dev/null)" || return 1
    version="$(plutil -extract CFBundleShortVersionString raw -o - "$plist" 2>/dev/null)" || return 1
    build="$(plutil -extract CFBundleVersion raw -o - "$plist" 2>/dev/null)" || return 1
    executable="$(plutil -extract CFBundleExecutable raw -o - "$plist" 2>/dev/null)" || return 1
    [ "$identifier" = com.jetbrains.intellij.ce ] && [ "$version" = "$EXPECTED_VERSION" ] || return 1
    [ -n "$build" ] && [ "$executable" = idea ] || return 1
    [ -f "$app/Contents/MacOS/idea" ] && [ -x "$app/Contents/MacOS/idea" ] || return 1
    printf '%s' "$build"
}

MOUNT_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/team-idea-mount.XXXXXXXX")" || die '无法创建 DMG 挂载临时目录'
MOUNT_POINT="$MOUNT_ROOT/volume"
mkdir "$MOUNT_POINT" || die '无法创建 DMG 挂载点'
# 先记录尝试，attach 部分成功后失败时也会尝试卸载这个专用挂载点。
MOUNT_ATTEMPTED=true
hdiutil attach -readonly -nobrowse -mountpoint "$MOUNT_POINT" "$DMG" || die '无法只读挂载 IDEA DMG'
SOURCE_APP="$MOUNT_POINT/$APP_NAME"
SOURCE_BUILD="$(bundle_build "$SOURCE_APP")" || die "DMG 中的 IDEA 应用不完整，或不是预期的社区版 ${EXPECTED_VERSION}。"

check_destination
if [ -d "$TARGET" ]; then
    if EXISTING_BUILD="$(bundle_build "$TARGET")" && [ "$EXISTING_BUILD" = "$SOURCE_BUILD" ]; then
        SUCCESS_MESSAGE="复用已验证的 IDEA 社区版 ${EXPECTED_VERSION}（${SOURCE_BUILD}）：$TARGET"
        exit 0
    fi
    die "已有 IDEA 版本、构建号不匹配或应用不完整；原应用已保留，请先自行处理后重试：$TARGET"
fi

mkdir -p -- "$APPLICATIONS" || die "无法创建用户应用目录：$APPLICATIONS"
check_destination
STAGING="$(mktemp -d "$APPLICATIONS/.idea-install.XXXXXXXX")" || die '无法创建用户目录内的安装暂存目录'
STAGED_APP="$STAGING/$APP_NAME"
ditto "$SOURCE_APP" "$STAGED_APP" || die '复制 IDEA 失败；未替换用户应用。'
COPIED_BUILD="$(bundle_build "$STAGED_APP")" || die '暂存的 IDEA 应用校验失败；未替换用户应用。'
[ "$COPIED_BUILD" = "$SOURCE_BUILD" ] || die '复制后的 IDEA 构建号不一致；未替换用户应用。'
check_destination
[ ! -e "$TARGET" ] || die "安装期间出现了同名应用，原应用已保留：$TARGET"
# 移动到父目录并禁止覆盖，避免并发出现的同名应用被替换或嵌套复制。
mv -n -- "$STAGED_APP" "$APPLICATIONS/" || die '无法保存 IDEA 到用户应用目录'
[ ! -e "$STAGED_APP" ] || die "安装期间出现了同名应用，原应用已保留：$TARGET"
SUCCESS_MESSAGE="IDEA 社区版 ${EXPECTED_VERSION} 已安装：${TARGET}（未启动）"
