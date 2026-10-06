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
    log 'Gradle Wrapper 配置已是目标值，无需修改'
    exit 0
fi
if [ ! -e "${WRAPPER_PROPERTIES}.bak" ]; then
    cp -p "$WRAPPER_PROPERTIES" "${WRAPPER_PROPERTIES}.bak"
fi
mv "$temp_file" "$WRAPPER_PROPERTIES"
chmod u+x "$PROJECT_DIR/gradlew"
log "Gradle Wrapper 已配置：$gradle_url"
log "初始备份：${WRAPPER_PROPERTIES}.bak"
log '已保留其他属性；请在加载 JDK 环境后进入项目执行 ./gradlew -v 验证。'
