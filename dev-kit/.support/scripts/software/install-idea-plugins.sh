#!/bin/bash
# 安装清单中已固定校验值的全部 IDEA 插件；不启动 IDEA、不执行插件代码。
set -euo pipefail
umask 022
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/common.sh"
source "$REPO_ROOT/scripts/lib/plugin-metadata.sh"

MODE=install
while [ "$#" -gt 0 ]; do
    case "$1" in
        --verify-only|--dry-run)
            [ "$MODE" = install ] || die '--verify-only 与 --dry-run 不能同时使用或重复指定'
            case "$1" in --verify-only) MODE=verify ;; --dry-run) MODE=preview ;; esac; shift ;;
        --help|-h)
            log '用法：install-idea-plugins.sh [--verify-only | --dry-run]'
            log '默认安装资源清单中全部 IDEA 插件；只读验证不会下载或修改插件。'
            log 'IDEA 必须先退出。已知旧插件先备份，未知插件与无关目录保留。'
            exit 0 ;;
        *) die "未知参数：$1" ;;
    esac
done
for tool in unzip xmllint plutil shasum find sort cmp mktemp ps ditto; do require_command "$tool"; done
USER_HOME="$(CDPATH= cd -- "$HOME" && pwd -P)"
IDEA_APP="${IDEA_APP:-$USER_HOME/Applications/IntelliJ IDEA CE.app}"
require_absolute_path IDEA_APP "$IDEA_APP"
while [ "${IDEA_APP%/}" != "$IDEA_APP" ]; do IDEA_APP="${IDEA_APP%/}"; done
plugin_safe_directory "$IDEA_APP" || exit 1
PLIST="$IDEA_APP/Contents/Info.plist"
[ -f "$PLIST" ] && [ ! -L "$PLIST" ] || die "IDEA 元数据缺失：$PLIST"
[ "$(plutil -extract CFBundleIdentifier raw -o - "$PLIST")" = com.jetbrains.intellij.ce ] || die '只支持目标 IDEA 社区版'
[ "$(plutil -extract CFBundleShortVersionString raw -o - "$PLIST")" = 2024.3.7.1 ] || die '需要先安装 IDEA 社区版 2024.3.7.1'
[ "$(plutil -extract CFBundleVersion raw -o - "$PLIST")" = IC-243.28141.41 ] || die 'IDEA 构建号与团队基线不一致'
[ -s "$IDEA_APP/Contents/MacOS/idea" ] && [ -x "$IDEA_APP/Contents/MacOS/idea" ] || die 'IDEA 启动文件不完整'
IDEA_BUILD=243.28141.41
SELECTOR=IdeaIC2024.3
if [ -f "$IDEA_APP/Contents/Resources/product-info.json" ]; then
    SELECTOR="$(plutil -extract dataDirectoryName raw -o - "$IDEA_APP/Contents/Resources/product-info.json")" || die '无法读取 IDEA 用户目录标识'
fi
[ "$SELECTOR" = IdeaIC2024.3 ] || die 'IDEA 用户目录标识与团队基线不一致'
PLUGINS_DIR="${IDEA_PLUGINS_DIR:-$USER_HOME/Library/Application Support/JetBrains/$SELECTOR/plugins}"
require_absolute_path IDEA_PLUGINS_DIR "$PLUGINS_DIR"
while [ "$PLUGINS_DIR" != / ] && [ "${PLUGINS_DIR%/}" != "$PLUGINS_DIR" ]; do PLUGINS_DIR="${PLUGINS_DIR%/}"; done
plugin_safe_directory "$PLUGINS_DIR" || exit 1
CATALOG="$REPO_ROOT/config/resources.tsv"
[ -f "$CATALOG" ] && [ ! -L "$CATALOG" ] || die '缺少已固定 SHA-256 的成员资源清单，请重新打包'

IDS=(); VERSIONS=(); PATHS=(); HASHES=(); STATUSES=(); TARGETS=(); BACKUPS=(); ROOTS=(); XML_IDS=(); ACTIONS=(); OLD_PATHS=()
COUNT=0
while IFS=$'\t' read -r rid group version arch relative url hash extra || [ -n "${rid:-}" ]; do
    case "${rid:-}" in ''|'#'*) continue ;; esac
    [ "$group" = plugins ] || continue
    [ -z "${extra:-}" ] && [ -n "$version" ] && [ -n "$relative" ] || die '插件清单字段不完整'
    case "$rid" in ''|*[!A-Za-z0-9._-]*) die '插件资源编号无效' ;; esac
    case "$version" in *[[:cntrl:]]*) die '插件版本含控制字符' ;; esac
    [ "$arch" = any ] || die "插件清单需要通用归档：$rid"
    plugin_safe_relative "$relative" || die "插件资源路径无效：$relative"
    [ -n "$hash" ] && [ "$hash" != - ] || die "插件尚未固定 SHA-256：${rid}，请重新准备并打包资源"
    validate_sha256 "$hash"
    hash="$(printf '%s' "$hash" | tr 'A-F' 'a-f')"
    prior=0
    while [ "$prior" -lt "$COUNT" ]; do
        [ "$rid" != "${IDS[$prior]}" ] && [ "$relative" != "${PATHS[$prior]}" ] || die '插件清单含重复编号或路径'
        prior=$((prior + 1))
    done
    IDS[$COUNT]="$rid"; VERSIONS[$COUNT]="$version"; PATHS[$COUNT]="$relative"; HASHES[$COUNT]="$hash"
    STATUSES[$COUNT]=not_run; TARGETS[$COUNT]='-'; BACKUPS[$COUNT]='-'; ACTIONS[$COUNT]=''; OLD_PATHS[$COUNT]=''; XML_IDS[$COUNT]=''; ROOTS[$COUNT]=''
    COUNT=$((COUNT + 1))
done < "$CATALOG"
[ "$COUNT" -gt 0 ] || die '资源清单中没有 IDEA 插件'
if [ "$MODE" = preview ]; then
    log "[预演] 将核验并安装全部 $COUNT 个插件到：$PLUGINS_DIR"
    index=0
    while [ "$index" -lt "$COUNT" ]; do log "[预演] ${IDS[$index]} ${VERSIONS[$index]}；已验证的相同版本复用，已知旧版本先备份。"; index=$((index + 1)); done
    log '[预演] 未下载、未创建插件目录、未启动 IDEA。'
    exit 0
fi

require_idea_stopped() {
    local processes
    processes="$(ps -axww -o comm=)" || die '无法确认 IDEA 是否正在运行，请退出 IDEA 后重试'
    if printf '%s\n' "$processes" | LC_ALL=C awk '/\/Contents\/MacOS\/idea[[:space:]]*$/ || /\/bin\/idea[[:space:]]*$/ {found=1} END {exit !found}'; then
        die 'IDEA 正在运行。请先完全退出 IDEA，再安装或验证插件；脚本不会强制结束进程。'
    fi
}
require_idea_stopped

WORK="$(mktemp -d "${TMPDIR:-/tmp}/team-idea-plugins.XXXXXXXX")"
TRANSACTION=''; ACTIVE=-1; BACKUP_RUN=''; RECEIPT_TEMP=''; ALL_VERIFIED=false
AUDIT_FILENAME=plugins-result.tsv
# 后续只读验证单独留档，保留本轮安装动作、旧版备份与修复证据。
if [ "$MODE" = verify ]; then AUDIT_FILENAME=plugins-verification.tsv; fi
mkdir "$WORK/scratch"
SCRATCH="$WORK/scratch"
cleanup() {
    code=$?
    trap - EXIT
    set +e
    if [ "$code" -ne 0 ] && [ "$ACTIVE" -ge 0 ]; then STATUSES[$ACTIVE]=failed; fi
    if [ -n "${REPAIR_RUN_DIR:-}" ] && [ -d "$REPAIR_RUN_DIR" ]; then
        if plugin_safe_directory "$REPAIR_RUN_DIR" && [ ! -L "$REPAIR_RUN_DIR/$AUDIT_FILENAME" ] && [ ! -d "$REPAIR_RUN_DIR/$AUDIT_FILENAME" ]; then
            {
                printf 'id\tversion\tstatus\tinstalledpath\tbackup\n'
                i=0
                while [ "$i" -lt "$COUNT" ]; do
                    printf '%s\t%s\t%s\t%s\t%s\n' "${IDS[$i]}" "${VERSIONS[$i]}" "${STATUSES[$i]}" "${TARGETS[$i]}" "${BACKUPS[$i]}"
                    i=$((i + 1))
                done
            } > "$WORK/$AUDIT_FILENAME"
            cp "$WORK/$AUDIT_FILENAME" "$REPAIR_RUN_DIR/$AUDIT_FILENAME" || code=1
        else printf '错误：插件审计结果路径无效，不能写入。\n' >&2; code=1; fi
    fi
    [ -z "$TRANSACTION" ] || rm -rf -- "$TRANSACTION" || code=1
    [ -z "$RECEIPT_TEMP" ] || rm -f -- "$RECEIPT_TEMP" || code=1
    rm -rf -- "$WORK" || code=1
    if [ "$code" -eq 0 ] && "$ALL_VERIFIED"; then
        log "全部插件验证通过：$COUNT 个。已验证归档来源、兼容范围、元数据、JAR 和安装文件收据。"
        log '请在下次启动 IDEA 后确认插件加载与启用；本次未启动 IDE，也未进行插件运行功能验收。'
    fi
    exit "$code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# 清点现有目录；损坏的已管理插件可用其本地收据识别，未知目录不被接管。
INV_PATHS=(); INV_IDS=(); INV_VERSIONS=(); INV_RESOURCES=(); INV_COUNT=0
for directory in "$PLUGINS_DIR"/*; do
    [ -d "$directory" ] && [ ! -L "$directory" ] || continue
    resource="$(plugin_receipt_identity "$directory" resource_id 2>/dev/null)" || resource=''
    if plugin_metadata "$directory" "$SCRATCH" 2>/dev/null; then
        identity="$PLUGIN_XML_ID"; installed_version="$PLUGIN_VERSION"
    else
        identity="$(plugin_receipt_identity "$directory" plugin_id 2>/dev/null)" || identity=''
        installed_version="$(plugin_receipt_identity "$directory" version 2>/dev/null)" || installed_version=''
    fi
    INV_PATHS[$INV_COUNT]="$directory"; INV_IDS[$INV_COUNT]="$identity"; INV_VERSIONS[$INV_COUNT]="$installed_version"; INV_RESOURCES[$INV_COUNT]="$resource"
    INV_COUNT=$((INV_COUNT + 1))
done

failures=0
index=0
while [ "$index" -lt "$COUNT" ]; do
    ACTIVE="$index"; rid="${IDS[$index]}"; version="${VERSIONS[$index]}"; hash="${HASHES[$index]}"
    existing=''; match_count=0; inv=0
    while [ "$inv" -lt "$INV_COUNT" ]; do
        if [ "${INV_RESOURCES[$inv]}" = "$rid" ]; then existing="${INV_PATHS[$inv]}"; match_count=$((match_count + 1)); fi
        inv=$((inv + 1))
    done
    [ "$match_count" -le 1 ] || die "发现多个同资源插件目录，原目录均已保留：$rid"
    if [ -n "$existing" ] && plugin_verify_installed "$existing" "$rid" "$version" "$hash" "$IDEA_BUILD" "$SCRATCH" 2>/dev/null; then
        TARGETS[$index]="$existing"; OLD_PATHS[$index]="$existing"; XML_IDS[$index]="$PLUGIN_XML_ID"; ACTIONS[$index]=reuse
        if [ "$MODE" = verify ]; then STATUSES[$index]=verified; else STATUSES[$index]=reused; fi
        log "[已验证] $rid ${version}：${existing}（收据、元数据与全部文件一致）"
    elif [ "$MODE" = verify ]; then
        STATUSES[$index]=failed; TARGETS[$index]="${existing:--}"; failures=$((failures + 1))
        log "[验证失败] $rid ${version}：插件缺失、内容不完整或与清单收据不一致。"
    else
        log "准备插件：$rid $version"
        /bin/bash "$REPO_ROOT/scripts/download-tools.sh" --id "$rid" || die "下载插件失败：$rid"
        archive="$USER_HOME/Downloads/team-java-env/${PATHS[$index]}"
        [ -f "$archive" ] && [ ! -L "$archive" ] || die "插件 ZIP 缺失或为符号链接：$archive"
        plugin_safe_directory "$(dirname -- "$archive")" || exit 1
        [ "$(plugin_hash "$archive")" = "$hash" ] || die "插件 ZIP SHA-256 不符：$rid"
        root="$(plugin_archive_root "$archive" "$SCRATCH")" || die "插件 ZIP 结构不安全：$rid"
        mkdir "$WORK/extract-$index"
        unzip -q "$archive" -d "$WORK/extract-$index" || die "无法解压插件：$rid"
        source_dir="$WORK/extract-$index/$root"
        plugin_make_receipt "$source_dir" "$rid" "$version" "$hash" "$IDEA_BUILD" "$WORK/receipt-$index" "$SCRATCH" || die "插件归档验证未通过：$rid"
        XML_IDS[$index]="$PLUGIN_XML_ID"; ROOTS[$index]="$root"
        target="$PLUGINS_DIR/$root"; TARGETS[$index]="$target"
        plugin_safe_directory "$target" || exit 1
        existing=''; match_count=0; inv=0; existing_version=''
        while [ "$inv" -lt "$INV_COUNT" ]; do
            if [ "${INV_IDS[$inv]}" = "$PLUGIN_XML_ID" ]; then
                existing="${INV_PATHS[$inv]}"; existing_version="${INV_VERSIONS[$inv]}"; match_count=$((match_count + 1))
            fi
            inv=$((inv + 1))
        done
        [ "$match_count" -le 1 ] || die "已有多个相同插件 ID，需先处理重复目录：$PLUGIN_XML_ID"
        if [ -e "$target" ] && [ "$target" != "$existing" ]; then die "目标是无关或无法识别的目录，已保留：$target"; fi
        OLD_PATHS[$index]="$existing"
        ACTIONS[$index]=installed
        if [ -n "$existing" ]; then
            if [ "$existing_version" = "$version" ]; then
                ACTIONS[$index]=repaired
                if plugin_make_receipt "$existing" "$rid" "$version" "$hash" "$IDEA_BUILD" "$WORK/existing-$index" "$SCRATCH" 2>/dev/null && cmp -s "$WORK/existing-$index" "$WORK/receipt-$index"; then
                    ACTIONS[$index]=adopt; TARGETS[$index]="$existing"
                fi
            else ACTIONS[$index]=upgraded; fi
        fi
    fi
    prior=0
    while [ "$prior" -lt "$index" ]; do
        if [ -n "${XML_IDS[$index]}" ]; then
            [ "${XML_IDS[$index]}" != "${XML_IDS[$prior]}" ] || die '清单中多个资源对应相同插件 ID'
            [ "${TARGETS[$index]}" != "${TARGETS[$prior]}" ] || die '清单中多个插件占用相同目录'
        fi
        prior=$((prior + 1))
    done
    index=$((index + 1))
done
ACTIVE=-1
if [ "$MODE" = verify ]; then
    [ "$failures" -eq 0 ] || exit 1
else
    # 所有归档及目标冲突均预检后，才创建同文件系统的暂存区。
    require_idea_stopped
    need_stage=false
    BACKUP_BASE="${IDEA_PLUGIN_BACKUP_DIR:-${REPAIR_RUN_DIR:-$USER_HOME/Library/Logs/team-java-env}/plugin-backups}"
    index=0
    while [ "$index" -lt "$COUNT" ]; do
        case "${ACTIONS[$index]}" in reuse|adopt) ;; *) need_stage=true ;; esac
        case "${ACTIONS[$index]}" in repaired|upgraded)
            require_absolute_path IDEA_PLUGIN_BACKUP_DIR "$BACKUP_BASE"
            plugin_safe_directory "$BACKUP_BASE" || exit 1 ;;
        esac
        index=$((index + 1))
    done
    if "$need_stage"; then
        mkdir -p -- "$PLUGINS_DIR"
        plugin_safe_directory "$PLUGINS_DIR" || exit 1
        TRANSACTION="$(mktemp -d "$PLUGINS_DIR/.team-plugin-install.XXXXXXXX")"
        mkdir "$TRANSACTION/staged"
    fi
    index=0
    while [ "$index" -lt "$COUNT" ]; do
        ACTIVE="$index"
        case "${ACTIONS[$index]}" in reuse|adopt) ;; *)
            root="${ROOTS[$index]}"
            ditto "$WORK/extract-$index/$root" "$TRANSACTION/staged/$root" || die '插件暂存复制失败'
            cp "$WORK/receipt-$index" "$TRANSACTION/staged/$root/$PLUGIN_RECEIPT"
            plugin_verify_installed "$TRANSACTION/staged/$root" "${IDS[$index]}" "${VERSIONS[$index]}" "${HASHES[$index]}" "$IDEA_BUILD" "$SCRATCH" || die '暂存插件验证失败' ;;
        esac
        index=$((index + 1))
    done
    index=0
    while [ "$index" -lt "$COUNT" ]; do
        ACTIVE="$index"; rid="${IDS[$index]}"; target="${TARGETS[$index]}"; existing="${OLD_PATHS[$index]}"; action="${ACTIONS[$index]}"
        require_idea_stopped
        plugin_safe_directory "$PLUGINS_DIR" || exit 1
        plugin_safe_directory "$target" || exit 1
        case "$action" in
            reuse) ;;
            adopt)
                [ ! -L "$target/$PLUGIN_RECEIPT" ] && [ ! -d "$target/$PLUGIN_RECEIPT" ] || die '本地收据目标冲突'
                RECEIPT_TEMP="$(mktemp "$target/.team-plugin-receipt.XXXXXXXX")"
                cp "$WORK/receipt-$index" "$RECEIPT_TEMP"
                mv -f -- "$RECEIPT_TEMP" "$target/$PLUGIN_RECEIPT"
                RECEIPT_TEMP=''
                STATUSES[$index]=reused ;;
            *)
                if [ -n "$existing" ]; then
                    plugin_safe_directory "$existing" || exit 1
                    if [ -z "$BACKUP_RUN" ]; then
                        require_absolute_path IDEA_PLUGIN_BACKUP_DIR "$BACKUP_BASE"
                        plugin_safe_directory "$BACKUP_BASE" || exit 1
                        mkdir -p -- "$BACKUP_BASE"
                        BACKUP_RUN="$(mktemp -d "$BACKUP_BASE/run.XXXXXXXX")"
                    fi
                    mkdir "$BACKUP_RUN/$rid"
                    BACKUPS[$index]="$BACKUP_RUN/$rid/${existing##*/}"
                    mv -n -- "$existing" "$BACKUP_RUN/$rid/" || die "无法备份已有插件：$rid"
                    [ ! -e "$existing" ] || die "插件备份未完成，原目录已保留：$existing"
                fi
                plugin_safe_directory "$target" || exit 1
                [ ! -e "$target" ] && [ ! -L "$target" ] || die "安装期间出现目标冲突，备份已保留：$target"
                staged="$TRANSACTION/staged/${ROOTS[$index]}"
                mv -n -- "$staged" "$PLUGINS_DIR/" || die "插件发布失败，已有备份保留在 ${BACKUPS[$index]}"
                [ ! -e "$staged" ] || die "插件发布冲突，原目录与备份均已保留：$target"
                STATUSES[$index]="$action" ;;
        esac
        plugin_verify_installed "$target" "$rid" "${VERSIONS[$index]}" "${HASHES[$index]}" "$IDEA_BUILD" "$SCRATCH" || die "安装后最终验证失败：${rid}；已有备份已保留"
        log "[已验证] $rid ${VERSIONS[$index]}：${target}（${STATUSES[$index]}）"
        index=$((index + 1))
    done
    ACTIVE=-1
fi
ALL_VERIFIED=true
