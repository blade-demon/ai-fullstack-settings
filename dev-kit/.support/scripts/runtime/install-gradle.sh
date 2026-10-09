#!/bin/bash
# 安装独立的用户 Gradle；指定项目时必须完成真实构建验证。
set -euo pipefail
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/common.sh"
source "$REPO_ROOT/scripts/lib/environment.sh"
source "$REPO_ROOT/scripts/lib/managed-env.sh"
CHECK_ONLY=false
arguments=()
for argument in "$@"; do
    if [ "$argument" = --check-only ]; then CHECK_ONLY=true
    else arguments+=("$argument"); fi
done
parse_args ${arguments[@]+"${arguments[@]}"}
if "$SHOW_HELP"; then
    log '用法：install-gradle.sh [--project 项目路径] [--dry-run]'
    log '安装独立 Gradle 并配置完整环境变量；指定项目后按 IDEA 的分发选择执行真实 build（含测试）。'
    exit 0
fi
VERSION_PATTERN='^[0-9][0-9A-Za-z.+_-]*$'
[[ "$GRADLE_VERSION" =~ $VERSION_PATTERN ]] || die 'GRADLE_VERSION 格式无效'
if [ -n "$PROJECT_DIR" ]; then
    [ -d "$PROJECT_DIR" ] || die "项目目录不存在：$PROJECT_DIR"
    PROJECT_DIR="$(CDPATH= cd -- "$PROJECT_DIR" && pwd -P)"
    [ -f "$PROJECT_DIR/build.gradle" ] || [ -f "$PROJECT_DIR/build.gradle.kts" ] || die '项目缺少 build.gradle 或 build.gradle.kts'
    TASK_PATTERN='^:?[A-Za-z0-9_][A-Za-z0-9_-]*(:[A-Za-z0-9_][A-Za-z0-9_-]*)*$'
    [[ "$GRADLE_BUILD_TASK" =~ $TASK_PATTERN ]] || die 'GRADLE_BUILD_TASK 必须是单一合法任务名，不能含空白或命令选项'
fi
require_absolute_path GRADLE_INSTALL_DIR "$GRADLE_INSTALL_DIR"
require_absolute_path GRADLE_USER_HOME "$GRADLE_USER_HOME"
managed_env_prepare_paths
gradle_url="$(package_url "$GRADLE_PACKAGE_PATH")"
GRADLE_SHA256="${GRADLE_SHA256:-$(resource_sha256 "$GRADLE_PACKAGE_PATH")}"
validate_sha256 "$GRADLE_SHA256"
if "$DRY_RUN"; then
    log '[预演] 检查完整 JDK 8（java、javac、jre）；本次不加载已生成环境或执行 SDK。'
    log "[预演] 通过固定 SHA-256 校验下载：$gradle_url"
    log "[预演] 安装/验证独立 Gradle：$GRADLE_INSTALL_DIR"
    log "[预演] 配置 GRADLE_HOME、$(gradle_alias_name)、GRADLE_USER_HOME 与 Java/Gradle PATH；当前 Java 切换到 JDK 8。"
    if [ -n "$PROJECT_DIR" ]; then
        log "[预演] 在 ${PROJECT_DIR} 按 IDEA 分发选择执行 Gradle --no-daemon --console=plain ${GRADLE_BUILD_TASK}。"
    else
        log '[预演] 未选择项目，不执行构建。'
    fi
    exit 0
fi

probe_jdk8
java_home="$PROBE_JDK_HOME"
if [ -z "$java_home" ]; then
    "$CHECK_ONLY" && [ "${GRADLE_JDK_PLANNED:-0}" = 1 ] || die '没有找到可用 JDK 8，请先配置 JDK 8'
else [ -d "$java_home/jre" ] || die 'JDK 8 缺少实际 jre 目录，无法配置完整环境'; fi
managed_install_target_check "$GRADLE_INSTALL_DIR" gradle
if [ ! -e "$GRADLE_INSTALL_DIR" ]; then
    [ -n "$GRADLE_SHA256" ] || die '新安装必须提供固定 SHA-256，未开始安装'
fi
for tool in curl tar shasum tee awk mktemp; do require_command "$tool"; done
temp_dir=''
cleanup() { [ -z "$temp_dir" ] || rm -rf -- "$temp_dir"; return 0; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

distribution_complete() {
    [ -d "$1" ] && [ ! -L "$1" ] && [ ! -L "$1/bin" ] && [ ! -L "$1/lib" ] &&
        [ -f "$1/bin/gradle" ] && [ -s "$1/bin/gradle" ] && [ -x "$1/bin/gradle" ] && [ ! -L "$1/bin/gradle" ] &&
        [ -f "$1/lib/gradle-launcher-$GRADLE_VERSION.jar" ] && [ -s "$1/lib/gradle-launcher-$GRADLE_VERSION.jar" ] &&
        [ ! -L "$1/lib/gradle-launcher-$GRADLE_VERSION.jar" ]
}
verify_version() {
    local candidate="$1" actual results
    log "验证 Gradle ${GRADLE_VERSION}：$candidate/bin/gradle --version"
    set +e
    (
        CDPATH= cd -- "$temp_dir" || exit 1
        export JAVA_HOME="$java_home" JAVA_8_HOME="$java_home" JRE_HOME="$java_home/jre"
        export GRADLE_HOME="$candidate" GRADLE_USER_HOME
        export PATH="$JAVA_HOME/bin:$GRADLE_HOME/bin:$PATH"
        "$candidate/bin/gradle" --version
    ) 2>&1 | tee "$temp_dir/version.log"
    results=("${PIPESTATUS[@]}")
    set -e
    if [ "${results[0]}" -ne 0 ]; then
        printf '错误：Gradle 版本命令失败（退出码 %s），原安装目录未覆盖。\n' "${results[0]}" >&2
        return "${results[0]}"
    fi
    [ "${results[1]}" -eq 0 ] || die '无法记录 Gradle 版本结果'
    actual="$(awk '/^Gradle[ \t]+/ {sub(/\r$/, ""); if (NF == 2) print $2}' "$temp_dir/version.log")"
    [ "$actual" = "$GRADLE_VERSION" ] || die "Gradle 版本不匹配：期望 ${GRADLE_VERSION}，实际 ${actual:-未找到版本标题}；原目录已保留。"
}

if [ -e "$GRADLE_INSTALL_DIR" ]; then
    distribution_complete "$GRADLE_INSTALL_DIR" || die "已有 Gradle 目录未知或不完整，不会覆盖：$GRADLE_INSTALL_DIR"
    observed="$(_probe_distribution_version "$GRADLE_INSTALL_DIR")" || die '已有 Gradle 分发结构或版本冲突'
    [ "$observed" = "$GRADLE_VERSION" ] || die "Gradle 版本冲突：期望 $GRADLE_VERSION，实际 $observed"
fi
if "$CHECK_ONLY"; then
    if [ -e "$GRADLE_INSTALL_DIR" ] && [ -n "$java_home" ]; then
        temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/gradle-preflight.XXXXXXXX")"
        GRADLE_USER_HOME="$temp_dir/user-home"
        verify_version "$GRADLE_INSTALL_DIR"
    elif [ -z "$java_home" ]; then log 'Gradle 运行验证待本计划提供 JDK 8；现有分发结构已检查。'; fi
    log 'Gradle 预检通过，未执行安装。'
    exit 0
fi

if [ -e "$GRADLE_INSTALL_DIR" ]; then
    distribution_complete "$GRADLE_INSTALL_DIR" || die "已有 Gradle 目录未知或不完整，不会覆盖：$GRADLE_INSTALL_DIR"
    temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/gradle-verify.XXXXXXXX")"
    gradle_home="$(CDPATH= cd -- "$GRADLE_INSTALL_DIR" && pwd -P)"
    verify_version "$gradle_home"
    log "复用已验证的 Gradle ${GRADLE_VERSION}：$gradle_home"
else
    [ -n "$GRADLE_SHA256" ] || die '新安装必须提供固定 SHA-256（成员清单或 GRADLE_SHA256），未开始下载'
    mkdir -p -- "$(dirname -- "$GRADLE_INSTALL_DIR")"
    install_parent="$(CDPATH= cd -- "$(dirname -- "$GRADLE_INSTALL_DIR")" && pwd -P)"
    GRADLE_INSTALL_DIR="$install_parent/${GRADLE_INSTALL_DIR##*/}"
    temp_dir="$(mktemp -d "$install_parent/.gradle-install.XXXXXXXX")"
    log "下载独立 Gradle：$gradle_url"
    team_download "$temp_dir/gradle.zip" "$gradle_url" --connect-timeout 15 --max-time 1200 || die 'Gradle 下载失败，未生成安装目录或环境配置'
    actual_sha="$(shasum -a 256 < "$temp_dir/gradle.zip")"
    actual_sha="${actual_sha%% *}"
    expected_sha="$(printf '%s' "$GRADLE_SHA256" | tr 'A-F' 'a-f')"
    [ "$actual_sha" = "$expected_sha" ] || die 'Gradle ZIP SHA-256 校验失败，未安装'
    tar -tf "$temp_dir/gradle.zip" > "$temp_dir/entries" || die 'Gradle ZIP 无法读取'
    awk -v root="gradle-$GRADLE_VERSION" '
        {count++; if ($0!=root && index($0,root "/")!=1) bad=1; if ($0 ~ /(^|\/)\.\.(\/|$)/ || $0 ~ /^\//) bad=1}
        END {exit (bad || !count)}
    ' "$temp_dir/entries" || die 'Gradle ZIP 包含不符合预期的目录或越界路径'
    tar -tvf "$temp_dir/gradle.zip" > "$temp_dir/types" || die 'Gradle ZIP 类型检查失败'
    awk 'substr($0,1,1)!="d" && substr($0,1,1)!="-" {exit 1}' "$temp_dir/types" || die 'Gradle ZIP 包含链接或特殊文件'
    mkdir "$temp_dir/payload" "$temp_dir/publish"
    tar -xf "$temp_dir/gradle.zip" -C "$temp_dir/payload" --no-same-owner || die 'Gradle ZIP 解压失败'
    candidate="$temp_dir/payload/gradle-$GRADLE_VERSION"
    distribution_complete "$candidate" || die 'Gradle 分发目录不完整（缺少可执行启动脚本或版本 launcher JAR）'
    verify_version "$candidate"
    printf '%s\n' '{"schema":1,"tool":"team-java-env","kind":"gradle"}' > "$candidate/.team-java-env-install.json" || die '无法写入 Gradle 安装来源标记，未发布安装'
    publish="$temp_dir/publish/${GRADLE_INSTALL_DIR##*/}"
    mv -- "$candidate" "$publish"
    [ ! -e "$GRADLE_INSTALL_DIR" ] && [ ! -L "$GRADLE_INSTALL_DIR" ] || die '安装期间目标目录已出现，原目录已保留'
    mv -n -- "$publish" "$install_parent/"
    [ ! -e "$publish" ] || die '安装期间目标目录已出现，原目录已保留'
    gradle_home="$GRADLE_INSTALL_DIR"
fi

managed_env_write_jdk "$java_home"
managed_env_write_gradle "$gradle_home"
if [ "${GRADLE_REGISTER_ONLY:-0}" = 1 ]; then
    log "Gradle ${GRADLE_VERSION} 已验证并登记；默认版本由完整组件计划统一设置。"
    exit 0
fi
expected_user_home="$GRADLE_USER_HOME"
(
    source "$ENV_FILE"
    [ "${JAVA_HOME:-}" = "$java_home" ] && [ "${JAVA_8_HOME:-}" = "$java_home" ] && [ "${JRE_HOME:-}" = "$java_home/jre" ] &&
        [ "${GRADLE_HOME:-}" = "$gradle_home" ] && [ "${GRADLE_USER_HOME:-}" = "$expected_user_home" ] && is_jdk8 "$JAVA_HOME" || exit 1
    case "$GRADLE_VERSION" in
        4.5.1) [ "${GRADLE_4_5_1_HOME:-}" = "$gradle_home" ] || exit 1 ;;
        6.8) [ "${GRADLE_6_8_HOME:-}" = "$gradle_home" ] || exit 1 ;;
    esac
    [ "$(command -v java)" = "$java_home/bin/java" ] && [ "$(command -v gradle)" = "$gradle_home/bin/gradle" ]
) || die '写入后加载环境验证失败，请检查受管环境文件中的自定义设置'
if [ -n "$PROJECT_DIR" ]; then
    /bin/bash "$REPO_ROOT/scripts/runtime/verify-gradle.sh" --project "$PROJECT_DIR"
    log "Gradle ${GRADLE_VERSION} 安装与终端项目构建验证通过；IDEA 项目设置和同步仍需确认。"
else
    log "Gradle ${GRADLE_VERSION} 已安装并验证；未选择项目，未执行构建。"
fi
log "当前终端先加载：source $(shell_quote "$ENV_FILE")（或新开终端）"
log "查看版本：gradle_use --list；当前终端切换：gradle_use $GRADLE_VERSION"
log "同时设为新终端默认：gradle_use $GRADLE_VERSION --default；验证：gradle --version"
