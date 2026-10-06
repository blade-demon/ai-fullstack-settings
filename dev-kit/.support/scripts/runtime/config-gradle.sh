#!/usr/bin/env bash
set -euo pipefail
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/common.sh"
parse_args "$@"
if "$SHOW_HELP"; then
    log '用法：bash scripts/runtime/config-gradle.sh --project 项目路径 [--dry-run]'
    log '配置已有 Wrapper 的下载地址，不安装全局 Gradle，也不运行项目。'
    exit 0
fi
check_wrapper
gradle_url="$(package_url "$GRADLE_PACKAGE_PATH")"
GRADLE_SHA256="${GRADLE_SHA256:-$(resource_sha256 "$GRADLE_PACKAGE_PATH")}"
validate_sha256 "$GRADLE_SHA256"
if "$DRY_RUN"; then
    log "[预演] Wrapper 配置：$WRAPPER_PROPERTIES"
    log "[预演] Gradle 下载地址：$gradle_url"
    exit 0
fi

# 只认可目标 URL 对应的完整解压缓存；其它 URL 的同版本缓存不能复用。
source "$REPO_ROOT/scripts/lib/environment.sh"
probe_gradle "$PROJECT_DIR" "$gradle_url"
if [ "$PROBE_GRADLE_STATE" = project_cached ]; then
    log "目标 URL 对应的 Gradle ${GRADLE_VERSION} 缓存完整，可离线复用：$PROBE_GRADLE_PATH"
else
    require_command curl
    log "检查 Gradle 安装包地址：$gradle_url"
    # HEAD 仅取响应头；禁止读取 curl 配置，限制连接、总时长与重定向协议。
    if ! http_status="$(curl --disable --head --fail --location --silent --show-error \
        --connect-timeout 5 --max-time 15 --proto '=http,https' --proto-redir '=http,https' \
        --output /dev/null --write-out '%{http_code}' "$gradle_url")"; then
        die "目标 Gradle 安装包不可达，未修改 Wrapper 配置、备份或权限：$gradle_url"
    fi
    case "$http_status" in
        2[0-9][0-9]) log "目标 Gradle 安装包地址可达（HTTP ${http_status}）。" ;;
        *) die "目标 Gradle 安装包未返回成功响应（HTTP ${http_status}），未修改 Wrapper 配置、备份或权限：$gradle_url" ;;
    esac
fi

temp_file="$(mktemp "${WRAPPER_PROPERTIES}.tmp.XXXXXX")"
trap 'rm -f "$temp_file"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# 保留权限；只改指定属性，同时折叠重复的同名键。
cp -p "$WRAPPER_PROPERTIES" "$temp_file"
GRADLE_CONFIG_URL="$gradle_url" GRADLE_CONFIG_SHA="$GRADLE_SHA256" awk '
    BEGIN {
        url=ENVIRON["GRADLE_CONFIG_URL"]
        sub(/:/, "\\:", url)
        sha=tolower(ENVIRON["GRADLE_CONFIG_SHA"])
    }
    /^[ \t]*distributionUrl([ \t]*[=:]|[ \t]+)/ {
        if (!seen_url++) print "distributionUrl=" url
        next
    }
    /^[ \t]*distributionSha256Sum([ \t]*[=:]|[ \t]+)/ && sha != "" {
        if (!seen_sha++) print "distributionSha256Sum=" sha
        next
    }
    {print}
    END {
        if (!seen_url) print "distributionUrl=" url
        if (sha != "" && !seen_sha) print "distributionSha256Sum=" sha
    }
' "$WRAPPER_PROPERTIES" > "$temp_file"
if cmp -s "$WRAPPER_PROPERTIES" "$temp_file"; then
    chmod u+x "$PROJECT_DIR/gradlew"
    log 'Gradle Wrapper 配置文件已是目标值，无需修改。'
    log '尚未运行实际 Wrapper；请在加载 JDK 环境后进入项目执行 ./gradlew -v 验证，并继续验证项目构建。'
    exit 0
fi
if [ ! -e "${WRAPPER_PROPERTIES}.bak" ]; then
    cp -p "$WRAPPER_PROPERTIES" "${WRAPPER_PROPERTIES}.bak"
fi
mv "$temp_file" "$WRAPPER_PROPERTIES"
chmod u+x "$PROJECT_DIR/gradlew"
log "Gradle Wrapper 配置文件已更新：$gradle_url"
log "初始备份：${WRAPPER_PROPERTIES}.bak"
log '已保留其他属性；尚未运行实际 Wrapper，请在加载 JDK 环境后进入项目执行 ./gradlew -v 验证，并继续验证项目构建。'
