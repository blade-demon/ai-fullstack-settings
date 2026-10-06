#!/bin/bash
# 只读检查 IDEA 的项目关联。使用 macOS 自带 XML 工具，不加载项目脚本或启动 IDE。
_idea_xml_valid() {
    safe_xml_valid "$1"
}

_idea_xml_value() {
    xmllint --nonet --xpath "string($2)" "$1" 2>/dev/null
}

_idea_expand_path() {
    local value="$1" project="$2" user_macro='$USER_HOME$' project_macro='$PROJECT_DIR$'
    value="${value//$user_macro/$HOME}"
    value="${value//$project_macro/$project}"
    case "$value" in *'$'*|*$'\n'*|*$'\r'*) return 1 ;; esac
    case "$value" in /*) printf '%s' "$value" ;; *) return 1 ;; esac
}

_idea_sdk_home() {
    local name="$1" project="$2" table="$3" count index candidate home type matches=0 result=''
    [ -n "$name" ] && _idea_xml_valid "$table" || return 1
    count="$(xmllint --nonet --xpath 'count(/application/component[@name="ProjectJdkTable"]/jdk)' "$table" 2>/dev/null)" || return 1
    case "$count" in ''|*[!0-9]*) return 1 ;; esac
    [ "$count" -le 256 ] || return 1
    for ((index=1; index<=count; index++)); do
        # 固定 XPath 按序号取值，SDK 名称（可能含引号）不插入 XPath。
        candidate="$(_idea_xml_value "$table" "/application/component[@name='ProjectJdkTable']/jdk[$index]/name/@value")" || return 1
        [ "$candidate" = "$name" ] || continue
        matches=$((matches + 1))
        type="$(_idea_xml_value "$table" "/application/component[@name='ProjectJdkTable']/jdk[$index]/type/@value")" || return 1
        [ "$type" = JavaSDK ] || return 1
        home="$(_idea_xml_value "$table" "/application/component[@name='ProjectJdkTable']/jdk[$index]/homePath/@value")" || return 1
        result="$(_idea_expand_path "$home" "$project")" || return 1
    done
    [ "$matches" -eq 1 ] && [ -x "$result/bin/java" ] && [ -x "$result/bin/javac" ] && is_jdk8 "$result" || return 1
    printf '%s' "$result"
}

probe_idea_project() {
    local project="${1:-}" purpose="${2:-configuration}" gradle misc table count index external selected='' type='' base sdk_home key cardinality
    PROBE_IDEA_PROJECT_STATE=not_selected
    PROBE_IDEA_PROJECT_NOTE=''
    PROBE_IDEA_PROJECT_SDK_NAME=''
    PROBE_IDEA_PROJECT_JVM=''
    PROBE_IDEA_PROJECT_JAVA_HOME=''
    PROBE_IDEA_PROJECT_DISTRIBUTION=unconfigured
    PROBE_IDEA_PROJECT_GRADLE_HOME=''
    [ -n "$project" ] || return 0
    PROBE_IDEA_PROJECT_STATE=pending
    if [ ! -d "$project" ]; then PROBE_IDEA_PROJECT_NOTE='项目目录不存在'; return 0; fi
    project="$(CDPATH= cd -- "$project" && pwd -P)" || return 0
    gradle="$project/.idea/gradle.xml"; misc="$project/.idea/misc.xml"
    if [ ! -e "$gradle" ] && [ ! -e "$misc" ]; then
        PROBE_IDEA_PROJECT_NOTE='尚未在 IDEA 中导入并配置项目'
        return 0
    fi
    PROBE_IDEA_PROJECT_DISTRIBUTION=unknown
    if ! command -v xmllint >/dev/null 2>&1 || ! _idea_xml_valid "$gradle"; then
        PROBE_IDEA_PROJECT_NOTE='无法安全解析 .idea/gradle.xml，请在 IDEA 中确认项目设置'
        return 0
    fi
    base='/project/component[@name="GradleSettings"]/option[@name="linkedExternalProjectsSettings"]/GradleProjectSettings'
    count="$(xmllint --nonet --xpath "count($base)" "$gradle" 2>/dev/null)" || count=''
    case "$count" in ''|*[!0-9]*) PROBE_IDEA_PROJECT_NOTE='无法解析关联的 Gradle 项目'; return 0 ;; esac
    if [ "$count" -gt 64 ]; then PROBE_IDEA_PROJECT_NOTE='关联项目过多，需在 IDEA 中确认'; return 0; fi
    for ((index=1; index<=count; index++)); do
        cardinality="$(xmllint --nonet --xpath "count($base[$index]/option[@name='externalProjectPath'])" "$gradle" 2>/dev/null)" || cardinality=''
        if [ "$cardinality" != 1 ]; then PROBE_IDEA_PROJECT_NOTE='Gradle 关联路径缺失或重复，无法确定分发设置'; return 0; fi
        external="$(_idea_xml_value "$gradle" "$base[$index]/option[@name='externalProjectPath']/@value")" || continue
        external="$(_idea_expand_path "$external" "$project")" || continue
        [ "$external" -ef "$project" ] || continue
        if [ -n "$selected" ]; then PROBE_IDEA_PROJECT_NOTE='项目存在重复的 Gradle 关联'; return 0; fi
        selected="$base[$index]"
    done
    if [ -z "$selected" ]; then PROBE_IDEA_PROJECT_NOTE='IDEA 尚未关联所选 Gradle 项目'; return 0; fi
    for key in distributionType gradleHome gradleJvm; do
        cardinality="$(xmllint --nonet --xpath "count($selected/option[@name='$key'])" "$gradle" 2>/dev/null)" || cardinality=''
        case "$cardinality" in
            0|1) ;;
            *) PROBE_IDEA_PROJECT_NOTE="Gradle 设置 ${key} 重复或无法解析，需在 IDEA 中确认"; return 0 ;;
        esac
    done
    type="$(_idea_xml_value "$gradle" "$selected/option[@name='distributionType']/@value")" || type=unknown
    case "$type" in
        ''|DEFAULT_WRAPPED|WRAPPED) PROBE_IDEA_PROJECT_DISTRIBUTION=wrapper ;;
        LOCAL)
            PROBE_IDEA_PROJECT_DISTRIBUTION=local
            external="$(_idea_xml_value "$gradle" "$selected/option[@name='gradleHome']/@value")" || external=''
            PROBE_IDEA_PROJECT_GRADLE_HOME="$(_idea_expand_path "$external" "$project")" || PROBE_IDEA_PROJECT_GRADLE_HOME=''
            ;;
        *) PROBE_IDEA_PROJECT_NOTE="Gradle 分发方式需确认：$type"; return 0 ;;
    esac
    # 构建选择和 dry-run 只读取分发信息，避免执行 IDEA 登记的 SDK。
    [ "$purpose" != distribution ] || return 0
    PROBE_IDEA_PROJECT_JVM="$(_idea_xml_value "$gradle" "$selected/option[@name='gradleJvm']/@value")" || PROBE_IDEA_PROJECT_JVM=''
    [ -n "$PROBE_IDEA_PROJECT_JVM" ] || PROBE_IDEA_PROJECT_JVM='#PROJECT'
    if ! _idea_xml_valid "$misc"; then PROBE_IDEA_PROJECT_NOTE='无法解析项目 SDK 设置 .idea/misc.xml'; return 0; fi
    type="$(_idea_xml_value "$misc" '/project/component[@name="ProjectRootManager"]/@project-jdk-type')" || type=''
    if [ "$type" != JavaSDK ]; then PROBE_IDEA_PROJECT_NOTE='项目 SDK 类型不是 JavaSDK，需在 Project Structure 中选择 JDK 8'; return 0; fi
    PROBE_IDEA_PROJECT_SDK_NAME="$(_idea_xml_value "$misc" '/project/component[@name="ProjectRootManager"]/@project-jdk-name')" || PROBE_IDEA_PROJECT_SDK_NAME=''
    table="${IDEA_CONFIG_DIR:-$HOME/Library/Application Support/JetBrains/IdeaIC2024.3}/options/jdk.table.xml"
    sdk_home="$(_idea_sdk_home "$PROBE_IDEA_PROJECT_SDK_NAME" "$project" "$table")" || {
        PROBE_IDEA_PROJECT_NOTE="项目 SDK 未登记、路径失效或不是 JDK 8；Gradle JVM=${PROBE_IDEA_PROJECT_JVM}"
        return 0
    }
    case "$PROBE_IDEA_PROJECT_JVM" in
        '#PROJECT') PROBE_IDEA_PROJECT_JAVA_HOME="$sdk_home" ;;
        '#'* ) PROBE_IDEA_PROJECT_NOTE="Gradle JVM ${PROBE_IDEA_PROJECT_JVM} 的图形环境解析需在 IDEA 中确认"; return 0 ;;
        *) PROBE_IDEA_PROJECT_JAVA_HOME="$(_idea_sdk_home "$PROBE_IDEA_PROJECT_JVM" "$project" "$table")" || {
            PROBE_IDEA_PROJECT_NOTE="Gradle JVM ${PROBE_IDEA_PROJECT_JVM} 未登记、路径失效或不是 JDK 8"
            return 0
        } ;;
    esac
    if [ "$PROBE_IDEA_PROJECT_DISTRIBUTION" = local ]; then
        external="$PROBE_IDEA_PROJECT_GRADLE_HOME"
        if [ -z "$external" ] || [ ! -x "$external/bin/gradle" ] || [ ! -s "$external/lib/gradle-launcher-${GRADLE_VERSION}.jar" ]; then
            PROBE_IDEA_PROJECT_NOTE="IDEA 本地 Gradle 目录未设置或缺少 Gradle ${GRADLE_VERSION}"
            return 0
        fi
    fi
    PROBE_IDEA_PROJECT_STATE=ready
}

report_idea_project() {
    case "$PROBE_IDEA_PROJECT_STATE" in
        not_selected) return 0 ;;
        ready)
            log "[IDEA 项目配置可解析] Project SDK=${PROBE_IDEA_PROJECT_SDK_NAME}；Gradle JVM=${PROBE_IDEA_PROJECT_JVM}"
            log "[IDEA 项目 JDK] $PROBE_IDEA_PROJECT_JAVA_HOME"
            log '[IDEA 同步待确认] 请执行 Reload All Gradle Projects；静态配置检查不代表图形界面已同步成功。'
            ;;
        *)
            log "[IDEA 项目待配置] $PROBE_IDEA_PROJECT_NOTE"
            log "[设置路径] File → Project Structure → Project → SDK：${PROBE_JDK_HOME:-先通过菜单 2 配置 JDK 8}"
            log '[设置路径] Settings → Build Tools → Gradle → Gradle JVM：明确选择同一个 JDK 8。'
            log "[本地 Gradle 安装参考] ${PROBE_CONFIG_GRADLE_HOME:-${GRADLE_HOME:-$GRADLE_INSTALL_DIR}}"
            ;;
    esac
    case "$PROBE_IDEA_PROJECT_DISTRIBUTION" in
        wrapper) log '[IDEA Gradle 分发] Wrapper；项目构建将验证 ./gradlew。' ;;
        local) log "[IDEA Gradle 分发] 本地安装：${PROBE_IDEA_PROJECT_GRADLE_HOME:-尚未设置}" ;;
        unconfigured) log '[IDEA Gradle 分发待设置] 导入项目后选择本地安装或已有 Wrapper，并重新同步。' ;;
    esac
}
