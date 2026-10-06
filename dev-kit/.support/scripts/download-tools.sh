#!/bin/bash
set -euo pipefail
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/lib" && pwd)/common.sh"
catalog="$REPO_ROOT/config/resources.tsv"
output="$(CDPATH= cd -- "$HOME" && pwd -P)/Downloads/team-java-env"
resource_id=''
list_only=false
preview=false
install_idea=false
while [ "$#" -gt 0 ]; do
    case "$1" in
        --id)
            [ "$#" -ge 2 ] && [ -n "$2" ] || die '--id 后需要资源编号'
            case "$2" in --*) die '--id 后需要资源编号' ;; esac
            resource_id="$2"; shift 2 ;;
        --list) list_only=true; shift ;;
        --install-idea) install_idea=true; shift ;;
        --dry-run) preview=true; shift ;;
        --help|-h)
            log '用法：download-tools.sh [--list] [--id 资源编号] [--dry-run] [--install-idea]'
            log '--install-idea 选择适配本机的 IDEA，下载后安装到当前用户的 ~/Applications。'
            exit 0 ;;
        *) die "未知参数：$1" ;;
    esac
done
[ -f "$catalog" ] || die '维护者尚未准备资源清单，请获取重新打包后的完整工具。'
case "$(uname -m)" in arm64|aarch64) machine_arch=arm64 ;; x86_64) machine_arch=x64 ;; *) die '不支持当前电脑架构' ;; esac
ids=(); groups=(); versions=(); arches=(); paths=(); hashes=()
tab=$'\t'
while IFS="$tab" read -r item group version arch relative url hash extra || [ -n "${item:-}" ]; do
    case "${item:-}" in ''|\#*) continue ;; esac
    case "$group" in software|plugins) ;; *) continue ;; esac
    if "$install_idea"; then
        [ "$group" = software ] || continue
        case "$item" in idea-*) ;; *) continue ;; esac
    fi
    [ "$arch" = any ] || [ "$arch" = "$machine_arch" ] || continue
    [ -z "${extra:-}" ] && [ -n "$relative" ] && [ -n "$hash" ] || die '资源清单损坏，请联系维护者重新打包。'
    case "$relative" in /*|..|../*|*/../*|*/..|*\\*) die '资源路径无效' ;; esac
    validate_sha256 "$hash"
    ids+=("$item"); groups+=("$group"); versions+=("$version"); arches+=("$arch")
    paths+=("$relative"); hashes+=("$hash")
done < "$catalog"
[ "${#ids[@]}" -gt 0 ] || die '当前没有适配此电脑的已准备资源，请联系维护者。'
if "$install_idea" && [ -z "$resource_id" ] && [ "${#ids[@]}" -eq 1 ]; then
    resource_id="${ids[0]}"
fi

display_name() {
    case "$1" in
        idea-*) printf 'IntelliJ IDEA 社区版' ;;
        dbeaver-*) printf 'DBeaver 社区版' ;;
        database-navigator) printf 'Database Navigator 插件' ;;
        mybatisx) printf 'MyBatisX 插件' ;;
        generate-all-setter) printf 'GenerateAllSetter 插件' ;;
        gsonformatplus) printf 'GsonFormatPlus 插件（JSON 转 Java 类）' ;;
        key-promoter-x) printf 'Key Promoter X 插件（快捷键提示）' ;;
        *) printf '%s' "$1" ;;
    esac
}
if [ -z "$resource_id" ] || "$list_only"; then
    log "适配当前电脑的资源（${machine_arch}）："
    for ((i=0; i<${#ids[@]}; i++)); do
        printf '%s. %s %s [%s]\n' "$((i+1))" "$(display_name "${ids[$i]}")" "${versions[$i]}" "${ids[$i]}"
    done
fi
"$list_only" && exit 0
if [ -z "$resource_id" ]; then
    printf '选择需要下载的软件/插件编号，0 返回：'
    IFS= read -r choice || exit 0
    [ "$choice" != 0 ] && [ -n "$choice" ] || exit 0
    case "$choice" in *[!0-9]*) die '请输入列表中的编号' ;; esac
    [ "${#choice}" -lt 5 ] || die '编号超出范围'
    choice=$((10#$choice))
    [ "$choice" -ge 1 ] && [ "$choice" -le "${#ids[@]}" ] || die '编号超出范围'
    resource_id="${ids[$((choice-1))]}"
fi
selected=-1
for ((i=0; i<${#ids[@]}; i++)); do
    if [ "${ids[$i]}" = "$resource_id" ]; then selected=$i; break; fi
done
[ "$selected" -ge 0 ] || die "未找到适配当前电脑的资源：$resource_id"
relative="${paths[$selected]}"
download_url="$(package_url "resources/$relative")"
if "$preview"; then
    log "[预演] 下载：$download_url"
    log "[预演] 保存：$output/$relative"
    if "$install_idea"; then
        log "[预演] 校验并安装到：$HOME/Applications/IntelliJ IDEA CE.app"
    fi
    exit 0
fi
fetcher="$REPO_ROOT/scripts/prepare-resources.sh"
[ -f "$fetcher" ] || die '下载组件缺失，请获取完整工具包'
if "$install_idea"; then
    [ -f "$REPO_ROOT/scripts/software/install-idea.sh" ] || die 'IDEA 安装组件缺失，请获取完整工具包'
fi
temporary="$(mktemp -d "${TMPDIR:-/tmp}/member-resources.XXXXXX")"
trap 'rm -rf "$temporary"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# 丢弃清单中的官网地址，成员始终只访问维护者配置的内网服务器。
printf '# id\tgroup\tversion\tarch\tpath\turl\tsha256\n' > "$temporary/catalog.tsv"
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$resource_id" "${groups[$selected]}" \
    "${versions[$selected]}" "${arches[$selected]}" "$relative" "$download_url" "${hashes[$selected]}" >> "$temporary/catalog.tsv"
/bin/bash "$fetcher" --catalog "$temporary/catalog.tsv" --output "$output" --id "$resource_id"
log "文件已准备好：$output/$relative"
if "$install_idea"; then
    /bin/bash "$REPO_ROOT/scripts/software/install-idea.sh" --dmg "$output/$relative" \
        --sha256 "${hashes[$selected]}" --version "${versions[$selected]}"
elif [ "${groups[$selected]}" = plugins ]; then
    log '在 IDEA 中打开 Settings → Plugins → 齿轮 → Install Plugin from Disk，选择此 ZIP；无需解压。'
else
    case "$resource_id" in
        idea-*)
            log "IDEA 安装到当前用户目录：$HOME/Applications。可返回主菜单选择 8 自动安装。"
            log '手动安装时，请复制 DMG 中的应用到个人 Applications，勿使用镜像内指向系统目录的 Applications 快捷方式。'
            ;;
        *) log '在 Finder 中打开上面的 DMG，按软件自身的安装提示操作。' ;;
    esac
fi
