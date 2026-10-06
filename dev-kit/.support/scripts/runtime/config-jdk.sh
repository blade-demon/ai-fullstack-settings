#!/usr/bin/env bash
set -euo pipefail
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/common.sh"
source "$REPO_ROOT/scripts/lib/environment.sh"
source "$REPO_ROOT/scripts/lib/managed-env.sh"
parse_args "$@"
if "$SHOW_HELP"; then
    log '用法：bash scripts/runtime/config-jdk.sh [--dry-run]'
    log '安装/复用 macOS JDK 8。配置见 config/env.sh，环境变量可覆盖。'
    exit 0
fi
[ -z "$PROJECT_DIR" ] || die 'JDK 脚本不接受 --project，请使用 install_env.sh'
[ "$(uname -s)" = Darwin ] || die '当前脚本面向 macOS'
case "$(uname -m)" in
    arm64|aarch64) jdk_arch=arm64 ;;
    x86_64) jdk_arch=x64 ;;
    *) die "不支持的 CPU 架构：$(uname -m)" ;;
esac
JDK_PACKAGE_PATH="${JDK_PACKAGE_PATH:-resources/runtime/jdk/jdk8-macos-${jdk_arch}.tar.gz}"
jdk_url="$(package_url "$JDK_PACKAGE_PATH")"
JDK_SHA256="${JDK_SHA256:-$(resource_sha256 "$JDK_PACKAGE_PATH")}"
validate_sha256 "$JDK_SHA256"
require_absolute_path JDK_INSTALL_DIR "$JDK_INSTALL_DIR"
managed_env_prepare_paths
case "$JDK_AUTO_DETECT" in true|false) ;; *) die 'JDK_AUTO_DETECT 只能为 true 或 false' ;; esac

if "$DRY_RUN"; then
    log "[预演] 架构：${jdk_arch}；JDK 包：$jdk_url"
    log "[预演] 安装/复用目录：$JDK_INSTALL_DIR"
    log "[预演] 环境文件：${ENV_FILE}；Shell 配置：$SHELL_PROFILE"
    exit 0
fi

temp_dir=''
env_temp=''
cleanup() {
    [ -z "$temp_dir" ] || rm -rf "$temp_dir"
    [ -z "$env_temp" ] || rm -f "$env_temp"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

probe_jdk8
if [ -n "$PROBE_JDK_HOME" ]; then
    java_home="$PROBE_JDK_HOME"
    log "复用 JDK 8：$java_home"
elif [ -e "$JDK_INSTALL_DIR" ] || [ -L "$JDK_INSTALL_DIR" ]; then
    die '现有安装目录不是可用的 JDK 8，且未找到其他可复用 JDK；不会覆盖，请选择另一个 JDK_INSTALL_DIR'
else
    require_command curl
    require_command tar
    if [ -n "$JDK_SHA256" ]; then require_command shasum; fi
    mkdir -p "$(dirname "$JDK_INSTALL_DIR")"
    temp_dir="$(mktemp -d "$(dirname "$JDK_INSTALL_DIR")/.jdk-install.XXXXXX")"
    log "下载 JDK：$jdk_url"
    if ! curl --fail --location --show-error --silent --connect-timeout 10 --max-time 600 \
        --retry 2 --proto '=http,https' --proto-redir '=http,https' \
        --output "$temp_dir/jdk.tar.gz" "$jdk_url"; then
        die "无法获取 JDK 安装包。请确认已连接公司网络或 VPN，并联系维护者检查：$jdk_url"
    fi
    if [ -n "$JDK_SHA256" ]; then
        actual_sha="$(shasum -a 256 "$temp_dir/jdk.tar.gz" | awk '{print $1}')"
        expected_sha="$(printf '%s' "$JDK_SHA256" | tr '[:upper:]' '[:lower:]')"
        [ "$actual_sha" = "$expected_sha" ] || die 'JDK 安装包 SHA-256 校验失败'
    fi
    tar -tzf "$temp_dir/jdk.tar.gz" > "$temp_dir/entries"
    if ! awk '/^\// || /(^|\/)\.\.(\/|$)/ {bad=1} END {exit bad}' "$temp_dir/entries"; then
        die '安装包包含越界路径'
    fi
    mkdir "$temp_dir/payload"
    tar -xzf "$temp_dir/jdk.tar.gz" -C "$temp_dir/payload"
    java_home="$(find_java_home "$temp_dir/payload")" || die '安装包中没有唯一、完整的 JDK（需包含 bin/java 和 bin/javac）'
    is_jdk8 "$java_home" || die '安装包不是可运行的 JDK 8，或 CPU 架构不匹配'
    [ -d "$java_home/jre" ] || die 'JDK 8 安装包缺少实际 jre 目录，未保存为安装结果'
    relative_home="${java_home#"$temp_dir/payload"}"
    # 同一文件系统内移动已验证的完整目录，失败时不留下半成品。
    [ ! -e "$JDK_INSTALL_DIR" ] || die '安装期间目标目录已被创建，请重试'
    ownership_marker="$temp_dir/payload/.team-java-env-install.json"
    [ ! -e "$ownership_marker" ] && [ ! -L "$ownership_marker" ] || die 'JDK 安装包包含保留的来源标记路径，未发布安装'
    printf '%s\n' '{"schema":1,"tool":"team-java-env","kind":"jdk"}' > "$ownership_marker" || die '无法写入 JDK 安装来源标记，未发布安装'
    mv "$temp_dir/payload" "$JDK_INSTALL_DIR"
    java_home="$JDK_INSTALL_DIR$relative_home"
fi

# 与后续探测使用相同的物理路径，避免 /var 与 /private/var 等别名导致重复改写。
java_home="$(CDPATH= cd -- "$java_home" && pwd -P)"
managed_env_write_jdk "$java_home"
(
    source "$ENV_FILE"
    [ "${JAVA_HOME:-}" = "$java_home" ] && [ "${JAVA_8_HOME:-}" = "$java_home" ] &&
        [ "${JRE_HOME:-}" = "$java_home/jre" ] && [ -d "$JRE_HOME" ] && is_jdk8 "$JAVA_HOME"
) || die 'JDK 环境加载验证失败，请检查 env.sh 受管区块之后的自定义覆盖设置'
log "JDK 8 已就绪：$java_home"
log "完整变量已配置：JAVA_HOME、JAVA_8_HOME、JRE_HOME；新终端自动加载。"
