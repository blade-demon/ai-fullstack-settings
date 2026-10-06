#!/usr/bin/env bash
# 公共函数兼容 macOS 自带 Bash 3.2；调用方启用 set -euo pipefail。
REPO_ROOT="$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../../config/env.sh
source "$REPO_ROOT/config/env.sh"

log() { printf '%s\n' "$*"; }
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
