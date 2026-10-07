#!/bin/bash
# 项目验证必须运行真实构建，不能以 --version 成功代替构建结果。
set -euo pipefail
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/common.sh"
source "$REPO_ROOT/scripts/lib/environment.sh"
source "$REPO_ROOT/scripts/lib/idea-project.sh"
parse_args "$@"
if "$SHOW_HELP"; then
    log '用法：verify-gradle.sh --project 项目路径 [--dry-run]'
    log '加载受管 JDK 8，按 IDEA 项目选择验证 Wrapper 或本地 Gradle，再执行 build（默认包含测试）。'
    exit 0
fi
[ -n "$PROJECT_DIR" ] && [ -d "$PROJECT_DIR" ] || die '请通过 --project 指定实际 Java 项目目录'
PROJECT_DIR="$(CDPATH= cd -- "$PROJECT_DIR" && pwd -P)"
[ -f "$PROJECT_DIR/build.gradle" ] || [ -f "$PROJECT_DIR/build.gradle.kts" ] || die '项目缺少 build.gradle 或 build.gradle.kts'
expected_version="$GRADLE_VERSION"
build_task="$GRADLE_BUILD_TASK"
TASK_PATTERN='^:?[A-Za-z0-9_][A-Za-z0-9_-]*(:[A-Za-z0-9_][A-Za-z0-9_-]*)*$'
[[ "$build_task" =~ $TASK_PATTERN ]] || die 'GRADLE_BUILD_TASK 必须是单一合法任务名，不能含空白、命令选项或命令替换'

# 只解析 IDEA 的分发选择，SDK 是否已登记不应改变要验证的 Gradle。
# 此模式不会运行 IDEA 的 java/javac，预演也不会执行任何 SDK。
probe_idea_project "$PROJECT_DIR" distribution
gradle_mode="$PROBE_IDEA_PROJECT_DISTRIBUTION"
gradle_command='${GRADLE_HOME}/bin/gradle'
case "$gradle_mode" in
    wrapper)
        check_wrapper
        [ -x "$PROJECT_DIR/gradlew" ] || die 'IDEA 选择了 Wrapper，但 gradlew 不可执行，请检查项目 Wrapper 文件权限'
        gradle_command="$PROJECT_DIR/gradlew"
        log "[IDEA Gradle 分发] Wrapper：$gradle_command"
        ;;
    local)
        idea_gradle_home="$PROBE_IDEA_PROJECT_GRADLE_HOME"
        [ -n "$idea_gradle_home" ] || die 'IDEA 本地 Gradle 待配置：gradleHome 未设置或无法解析，请检查 Settings → Build Tools → Gradle 的本地安装目录'
        distribution_version="$(_probe_distribution_version "$idea_gradle_home")" || distribution_version=''
        [ "$distribution_version" = "$expected_version" ] || die "IDEA gradleHome 缺少 Gradle ${expected_version} 完整分发，请检查 Settings → Build Tools → Gradle：$idea_gradle_home"
        gradle_command="$idea_gradle_home/bin/gradle"
        log "[IDEA Gradle 分发] 本地安装：$idea_gradle_home"
        ;;
    unconfigured)
        log '[IDEA 项目未配置] 尚未关联 IDEA Gradle 项目；本次验证受管独立 Gradle，IDEA 配置和同步待确认。'
        ;;
    *)
        die "无法确定 IDEA 项目的 Gradle 分发：${PROBE_IDEA_PROJECT_NOTE:-配置未知}；请检查 Settings → Build Tools → Gradle 的分发设置"
        ;;
esac
if "$DRY_RUN"; then
    log "[预演] 将加载受管环境并验证 JDK 8：${ENV_FILE}；本次不加载环境或执行 SDK。"
    log "[预演] 先验证目标 Gradle ${expected_version}：$gradle_command --version"
    log "[预演] 在 ${PROJECT_DIR} 执行 $gradle_command --no-daemon --console=plain ${build_task}。"
    log '[预演] 只有退出码为 0 且存在 BUILD SUCCESSFUL 才报告构建通过；本次不执行。'
    exit 0
fi
[ -f "$ENV_FILE" ] || die "缺少受管环境文件，请先完成 JDK/Gradle 安装：$ENV_FILE"
source "$ENV_FILE" || die '受管环境加载失败'
[ -n "${JAVA_HOME:-}" ] && [ "${JAVA_8_HOME:-}" = "$JAVA_HOME" ] &&
    [ "${JRE_HOME:-}" = "$JAVA_HOME/jre" ] && [ -d "$JRE_HOME" ] || die 'JDK 完整环境变量缺失或不一致，请先修复 JDK 环境'
is_jdk8 "$JAVA_HOME" || die 'JAVA_HOME 不是可用的完整 JDK 8（java 与 javac 均需 1.8）'
[ -n "${GRADLE_USER_HOME:-}" ] || die 'GRADLE_USER_HOME 未配置'
case "$gradle_mode" in
    local) GRADLE_HOME="$idea_gradle_home" ;;
    unconfigured)
        [ -n "${GRADLE_HOME:-}" ] && [ -s "$GRADLE_HOME/bin/gradle" ] && [ -x "$GRADLE_HOME/bin/gradle" ] &&
            [ -s "$GRADLE_HOME/lib/gradle-launcher-$expected_version.jar" ] || die 'GRADLE_HOME 缺少指定版本的完整 Gradle 分发'
        case "$expected_version" in
            4.5.1) [ "${GRADLE_4_5_1_HOME:-}" = "$GRADLE_HOME" ] || die 'GRADLE_4_5_1_HOME 与 GRADLE_HOME 不一致' ;;
            6.8) [ "${GRADLE_6_8_HOME:-}" = "$GRADLE_HOME" ] || die 'GRADLE_6_8_HOME 与 GRADLE_HOME 不一致' ;;
        esac
        gradle_command="$GRADLE_HOME/bin/gradle"
        ;;
esac
export JAVA_HOME JAVA_8_HOME JRE_HOME GRADLE_USER_HOME
if [ "$gradle_mode" = wrapper ]; then
    export PATH="$JAVA_HOME/bin:$PATH"
else
    export GRADLE_HOME
    export PATH="$JAVA_HOME/bin:$GRADLE_HOME/bin:$PATH"
fi
for tool in tee awk mktemp; do require_command "$tool"; done
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/gradle-build-verify.XXXXXXXX")" || die '无法创建构建验证输出目录'
trap 'rm -rf -- "$work_dir"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

run_gradle() {
    local output="$1" results
    shift
    set +e
    (
        CDPATH= cd -- "$PROJECT_DIR" || exit 1
        "$gradle_command" "$@"
    ) 2>&1 | tee "$output"
    results=("${PIPESTATUS[@]}")
    set -e
    GRADLE_LAST_EXIT="${results[0]}"
    if [ "${results[0]}" -ne 0 ]; then return "${results[0]}"; fi
    [ "${results[1]}" -eq 0 ] || die '构建输出记录失败，不能确认完整结果'
    return 0
}

log "验证目标 Gradle ${expected_version}：$gradle_command --version"
if run_gradle "$work_dir/version.log" --version; then
    :
else
    status=$?
    printf '错误：Gradle 版本验证退出码：%s\n' "$status" >&2
    exit "$status"
fi
actual_version="$(awk '/^Gradle[ \t]+/ {sub(/\r$/, ""); if (NF == 2) print $2}' "$work_dir/version.log")"
[ "$actual_version" = "$expected_version" ] || die "Gradle 版本验证失败：期望 ${expected_version}，实际 ${actual_version:-未找到版本标题}。"
log "执行项目构建：$PROJECT_DIR"
log "命令：$gradle_command --no-daemon --console=plain $build_task"
if run_gradle "$work_dir/build.log" --no-daemon --console=plain "$build_task"; then
    log 'Gradle 构建退出码：0'
else
    status=$?
    printf '错误：Gradle 构建退出码：%s；构建验证未通过。\n' "$status" >&2
    exit "$status"
fi
awk '{sub(/\r$/, ""); if ($0 == "BUILD SUCCESSFUL" || $0 ~ /^BUILD SUCCESSFUL in .+$/) found=1} END {exit !found}' \
    "$work_dir/build.log" || die 'Gradle 虽然退出 0，但没有 BUILD SUCCESSFUL 标记，不能宣称构建通过'
log "项目构建验证通过（仅终端）：${PROJECT_DIR}；任务 ${build_task}，退出码 0，已确认 BUILD SUCCESSFUL。"
log '[IDEA 同步待确认] 请在 IDEA 中确认项目 SDK、Gradle JVM 与分发设置，并执行 Reload All Gradle Projects。'
