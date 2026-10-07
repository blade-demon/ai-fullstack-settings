#!/usr/bin/env bash
# 公共函数兼容 macOS 自带 Bash 3.2；调用方启用 set -euo pipefail。
REPO_ROOT="$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../../config/env.sh
source "$REPO_ROOT/config/env.sh"

log() { printf '%s\n' "$*"; }
team_tui_stage() {
    [ "${TEAM_TUI_EVENTS:-0}" = 1 ] || return 0
    local id="$1" status="$2" title="$3"
    id="${id//$'\t'/ }"; id="${id//$'\n'/ }"; id="${id//$'\r'/ }"
    title="${title//$'\t'/ }"; title="${title//$'\n'/ }"; title="${title//$'\r'/ }"
    printf '@@TEAM_TUI\tstage\t%s\t%s\t%s\n' "$id" "$status" "$title"
}
die() { printf '错误：%s\n' "$*" >&2; exit 1; }
require_command() { command -v "$1" >/dev/null 2>&1 || die "缺少命令：$1"; }

# 单引号转义不受终端 locale 影响，Bash/Zsh 均可加载，中文路径保持可读。
shell_quote() {
    local single_quote="'" escaped_single_quote="'\\''"
    printf "'%s'" "${1//$single_quote/$escaped_single_quote}"
}

parse_args() {
    DRY_RUN=false
    SHOW_HELP=false
    PROJECT_DIR=''
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --dry-run) DRY_RUN=true; shift ;;
            --help|-h) SHOW_HELP=true; shift ;;
            --project)
                [ "$#" -ge 2 ] && [ -n "$2" ] || die '--project 后需要项目路径'
                case "$2" in --*) die '--project 后需要项目路径' ;; esac
                PROJECT_DIR="$2"; shift 2 ;;
            *) die "未知参数：$1（使用 --help 查看用法）" ;;
        esac
    done
}

validate_server() {
    case "$SERVER_SCHEME" in http|https) ;; *) die 'SERVER_SCHEME 只能为 http 或 https' ;; esac
    case "$SERVER_ADDR" in
        ''|*[[:space:]/\\\?\#@]*) die 'SERVER_ADDR 应为主机:端口，不包含协议、路径或空白' ;;
    esac
}

package_url() {
    validate_server
    case "$1" in
        ''|*[!a-zA-Z0-9._/+%-]*) die '安装包路径仅支持字母、数字、/、.、_、+、%、-，特殊字符请 URL 编码' ;;
    esac
    printf '%s://%s/%s\n' "$SERVER_SCHEME" "$SERVER_ADDR" "${1#/}"
}

validate_sha256() {
    [ -n "$1" ] || return 0
    [ "${#1}" -eq 64 ] || die 'SHA-256 必须是 64 位十六进制值'
    case "$1" in *[!0-9a-fA-F]*) die 'SHA-256 必须是 64 位十六进制值' ;; esac
}

# 正式分发包的清单由维护者对实际文件校验后生成；自定义路径无匹配时留空。
resource_sha256() {
    local catalog="$REPO_ROOT/config/resources.tsv"
    [ -f "$catalog" ] || return 0
    case "$1" in resources/*) ;; *) return 0 ;; esac
    awk -F '\t' -v path="${1#resources/}" '$0 !~ /^#/ && $5 == path && $7 != "-" {print $7; exit}' "$catalog"
}

require_absolute_path() {
    case "$2" in /*) ;; *) die "$1 必须为绝对路径：$2" ;; esac
    case "$2" in *$'\n'*|*$'\r'*) die "$1 不支持换行符" ;; esac
}

check_wrapper() {
    [ -n "$PROJECT_DIR" ] || die '请通过 --project 指定现有 Java 项目'
    [ -d "$PROJECT_DIR" ] || die "项目目录不存在：$PROJECT_DIR"
    PROJECT_DIR="$(CDPATH= cd -- "$PROJECT_DIR" && pwd)"
    local relative
    for relative in gradlew gradle/wrapper/gradle-wrapper.jar gradle/wrapper/gradle-wrapper.properties; do
        [ -s "$PROJECT_DIR/$relative" ] || die "缺少 Wrapper 文件：$PROJECT_DIR/${relative}；请从项目仓库取得完整 Wrapper"
    done
    WRAPPER_PROPERTIES="$PROJECT_DIR/gradle/wrapper/gradle-wrapper.properties"
    [ ! -L "$WRAPPER_PROPERTIES" ] || die 'Wrapper 配置是符号链接，请直接指定真实项目配置'
}

find_java_home() {
    local base="$1" candidate found=''
    if [ -x "$base/bin/java" ] && [ -x "$base/bin/javac" ]; then
        printf '%s\n' "$base"
        return 0
    fi
    [ -d "$base" ] || return 1
    while IFS= read -r candidate; do
        [ -x "$candidate" ] && [ -x "${candidate%/java}/javac" ] || continue
        [ -z "$found" ] || return 1
        found="${candidate%/bin/java}"
    done < <(find "$base" -type f -path '*/bin/java')
    [ -n "$found" ] || return 1
    printf '%s\n' "$found"
}

is_jdk8() {
    local java_version javac_version
    java_version=$("$1/bin/java" -version 2>&1) || return 1
    javac_version=$("$1/bin/javac" -version 2>&1) || return 1
    [[ "$java_version" =~ version[[:space:]]\"1\.8\. ]] &&
        [[ "$javac_version" =~ javac[[:space:]]1\.8\. ]]
}

# 为各版本保留独立环境变量别名。
gradle_alias_name() {
    local version="${1:-$GRADLE_VERSION}"
    printf 'GRADLE_%s_HOME\n' "${version//./_}"
}

# IDEA XML 的统一只读安全入口：先以已知编码解码检查，再交给 XML 解析器。
# --nonet 不禁止本地外部实体；不能让解析器先解码未检查的 UTF-7/EBCDIC 等内容。
safe_xml_valid() (
    set -o pipefail
    local file="$1" magic encoding=UTF-8 decoder=UTF-8 bom=false
    [ -f "$file" ] && [ ! -L "$file" ] || return 1
    command -v iconv >/dev/null 2>&1 && command -v xmllint >/dev/null 2>&1 || return 1
    magic="$(LC_ALL=C od -An -tx1 -N4 "$file" 2>/dev/null | LC_ALL=C tr -d ' \n')" || return 1
    case "$magic" in
        # UTF-32 和不常见字节序明确拒绝，不依赖宿主 libxml 的可选编码支持。
        0000feff|fffe0000|0000003c|3c000000|00003c00|003c0000) return 1 ;;
        feff*) encoding=UTF-16BE; decoder=UTF-16; bom=true ;;
        fffe*) encoding=UTF-16LE; decoder=UTF-16; bom=true ;;
        003c003f) encoding=UTF-16BE; decoder=UTF-16BE ;;
        3c003f00) encoding=UTF-16LE; decoder=UTF-16LE ;;
        *)
            # UTF-8/ASCII 不含 NUL；避免未识别的 UTF-16 被 libxml 再次自动探测。
            LC_ALL=C tr -d '\000' < "$file" | cmp -s "$file" - || return 1 ;;
    esac
    # iconv 只处理候选文件字节，不解析 XML、不读外部实体、不写临时文件。
    iconv -f "$decoder" -t UTF-8 "$file" 2>/dev/null | LC_ALL=C awk -v actual="$encoding" -v bom="$bom" '
        {document=document $0 "\n"}
        END {
            sub(/^\357\273\277/, "", document)
            if (document ~ /<!DOCTYPE|<!ENTITY/) exit 1
            sub(/^[ \t\r\n]*/, "", document)
            if (substr(document, 1, 1) != "<") exit 1
            declared=""
            if (document ~ /^<\?xml[ \t\r\n]/) {
                end=index(document, "?>")
                if (!end) exit 1
                declaration=substr(document, 1, end+1)
                if (match(declaration, /encoding[ \t\r\n]*=[ \t\r\n]*["\047][^"\047]*["\047]/)) {
                    declared=substr(declaration, RSTART, RLENGTH)
                    sub(/^[^=]*=[ \t\r\n]*["\047]/, "", declared)
                    sub(/["\047]$/, "", declared)
                    declared=toupper(declared)
                }
            }
            if (actual == "UTF-8") {
                if (declared != "" && declared != "UTF-8" && declared != "ASCII" && declared != "US-ASCII") exit 1
            } else {
                if (declared != actual && !(bom == "true" && (declared == "" || declared == "UTF-16"))) exit 1
            }
        }
    ' || return 1
    xmllint --nonet --noout "$file" >/dev/null 2>&1
)
