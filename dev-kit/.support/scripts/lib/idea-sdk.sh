#!/bin/bash
# Bash 3.2 + 系统 XML 工具；所有内容预检、暂存完成后才发布。

idea_sdk_register_global() (
    local table="$IDEA_CONFIG_DIR/options/jdk.table.xml" work='' stage='' input count index name kind sdk_home had_table=false
    local IDEA_SYNC_HOME=''
    _idea_sync_safe_path "$table"
    _idea_sync_stopped
    if "$DRY_RUN"; then log "[预演] 已有可用 JDK 时登记 IDEA SDK：$table；不修改业务项目。"; return 0; fi
    probe_jdk8
    if [ -z "$PROBE_JDK_HOME" ]; then log '[IDEA SDK 待配置] 尚无可用 JDK；应用与插件可以独立使用。'; return 2; fi
    IDEA_SYNC_HOME="$(CDPATH= cd -- "$PROBE_JDK_HOME" && pwd -P)" || return 1
    if [ -e "$table" ]; then
        had_table=true
        _idea_sync_xml "$table" application
        case "$(_idea_sync_count "$table" '/application/component[@name="ProjectJdkTable"]')" in 0|1) ;; *) die 'ProjectJdkTable 重复' ;; esac
        count="$(_idea_sync_count "$table" '/application/component[@name="ProjectJdkTable"]/jdk')"
        case "$count" in ''|*[!0-9]*) die 'SDK 登记数量无效' ;; esac
        [ "$count" -le 256 ] || die 'SDK 登记过多'
        for ((index=1;index<=count;index++)); do
            for kind in name type homePath; do _idea_sync_one "$table" "/application/component[@name='ProjectJdkTable']/jdk[$index]/$kind" "SDK $kind"; done
            kind="$(_idea_xml_value "$table" "/application/component[@name='ProjectJdkTable']/jdk[$index]/type/@value")"
            name="$(_idea_xml_value "$table" "/application/component[@name='ProjectJdkTable']/jdk[$index]/name/@value")"
            sdk_home="$(_idea_xml_value "$table" "/application/component[@name='ProjectJdkTable']/jdk[$index]/homePath/@value")"
            sdk_home="$(_idea_expand_path "$sdk_home" "$HOME")" || sdk_home=''
            if [ "$kind" = JavaSDK ] && [ -n "$sdk_home" ] && [ "$sdk_home" -ef "$IDEA_SYNC_HOME" ]; then
                [ "$(_idea_sync_count "$table" "/application/component[@name='ProjectJdkTable']/jdk[$index]/roots/classPath/root/root")" -gt 0 ] || die '已有 SDK roots 不完整，请在 IDEA 中修复'
                log "已复用 IDEA JDK 登记：$name → $IDEA_SYNC_HOME"; return 0
            fi
            [ "$name" != "$IDEA_JDK_NAME" ] || die "SDK 名称 $IDEA_JDK_NAME 已被其他目录使用，原配置保留"
        done
    fi
    work="$(mktemp -d "${TMPDIR:-/tmp}/idea-global-sdk.XXXXXXXX")" || return 1
    trap 'status=$?; [ -z "$stage" ] || rm -f -- "$stage"; rm -rf -- "$work"; exit "$status"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    if [ -f "$table" ]; then cp -p "$table" "$work/input.xml"; else printf '<application><component name="ProjectJdkTable"/></application>' > "$work/input.xml"; fi
    cp "$REPO_ROOT/scripts/lib/idea-sdk-sync.xsl" "$work/sync.xsl"
    {
        printf '<plan name="%s" home="%s" keep-index="0" gradle-index="0">' "$(_idea_sync_escape "$IDEA_JDK_NAME")" "$(_idea_sync_escape "$IDEA_SYNC_HOME")"
        _idea_sync_new_sdk
        printf '</plan>'
    } > "$work/plan.xml"
    _idea_xml_valid "$work/plan.xml" || die 'SDK 计划无效'
    xsltproc --nonet "$work/sync.xsl" "$work/input.xml" > "$work/output.xml" || die 'SDK 登记准备失败'
    _idea_xml_valid "$work/output.xml" || die 'SDK 登记结果无效'
    _idea_sync_stopped
    _idea_sync_safe_path "$table"
    if "$had_table"; then cmp -s "$table" "$work/input.xml" || die 'IDEA 配置已变化，未写入'
    else [ ! -e "$table" ] || die 'IDEA 配置已出现，原文件保留'; fi
    mkdir -p "$(dirname -- "$table")"
    _idea_sync_safe_path "$table.bak"
    if [ -f "$table" ] && [ ! -e "$table.bak" ]; then cp -p "$table" "$table.bak"; fi
    stage="$(mktemp "$(dirname -- "$table")/.idea-sdk.XXXXXXXX")" || return 1
    cp "$work/output.xml" "$stage" && mv -f "$stage" "$table" || die 'SDK 登记发布失败'
    stage=''
    log "已登记 IDEA JDK：${IDEA_JDK_NAME} → ${IDEA_SYNC_HOME}；未修改项目。"
)
_idea_sync_safe_path() {
    local path="$1"
    require_absolute_path 'IDEA 配置路径' "$path"
    while [ "$path" != / ]; do
        [ ! -L "$path" ] || die "IDEA 配置路径包含符号链接：$path"
        if [ -e "$path" ] && [ ! -d "$path" ] && [ "$path" != "$1" ]; then die "IDEA 配置父路径不是目录：$path"; fi
        path="$(dirname -- "$path")"
    done
}

_idea_sync_stopped() {
    local processes
    processes="$(ps -axww -o comm=)" || die '无法确认 IDEA 是否运行，请退出 IDEA 后重试'
    if printf '%s\n' "$processes" | LC_ALL=C awk '/\/Contents\/MacOS\/idea[[:space:]]*$/ || /\/bin\/idea[[:space:]]*$/ {found=1} END {exit !found}'; then
        die 'IDEA 正在运行。请完全退出 IDEA 后再同步 SDK 配置'
    fi
}

_idea_sync_count() {
    xmllint --nonet --xpath "count($2)" "$1" 2>/dev/null
}

_idea_sync_one() {
    [ "$(_idea_sync_count "$1" "$2")" = 1 ] || die "IDEA XML 设置缺失或重复：$3"
}

_idea_sync_xml() {
    _idea_sync_safe_path "$1"
    _idea_xml_valid "$1" || die "无法安全解析 IDEA XML（畸形、DTD 或实体声明）：$1"
    _idea_sync_one "$1" "/$2" "$1 的根元素"
    [ "$(_idea_sync_count "$1" '/*')" = 1 ] || die "IDEA XML 根元素不明确：$1"
}

_idea_sync_escape() {
    printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' -e 's/"/\&quot;/g'
}

_idea_sync_alias() {
    local value="$1" existing
    [ -n "$value" ] || return 0
    for existing in ${IDEA_SYNC_ALIASES[@]+"${IDEA_SYNC_ALIASES[@]}"}; do [ "$existing" != "$value" ] || return 0; done
    IDEA_SYNC_ALIASES+=("$value")
}

_idea_sync_project() {
    local project="$1" misc="$2" gradle="$3" count index xpath external key selected=0 old_name
    _idea_sync_xml "$misc" project
    _idea_sync_one "$misc" '/project/component[@name="ProjectRootManager"]' 'ProjectRootManager'
    IDEA_SYNC_OLD_PROJECT_NAME="$(_idea_xml_value "$misc" '/project/component[@name="ProjectRootManager"]/@project-jdk-name')"
    _idea_sync_xml "$gradle" project
    _idea_sync_one "$gradle" '/project/component[@name="GradleSettings"]' 'GradleSettings'
    _idea_sync_one "$gradle" '/project/component[@name="GradleSettings"]/option[@name="linkedExternalProjectsSettings"]' 'linkedExternalProjectsSettings'
    xpath='/project/component[@name="GradleSettings"]/option[@name="linkedExternalProjectsSettings"]/GradleProjectSettings'
    count="$(_idea_sync_count "$gradle" "$xpath")"
    case "$count" in ''|*[!0-9]*) die '无法解析 Gradle 关联' ;; esac
    [ "$count" -le 64 ] || die 'Gradle 关联过多，无法确定当前项目'
    for ((index=1; index<=count; index++)); do
        _idea_sync_one "$gradle" "$xpath[$index]/option[@name='externalProjectPath']" 'Gradle externalProjectPath'
        external="$(_idea_xml_value "$gradle" "$xpath[$index]/option[@name='externalProjectPath']/@value")"
        external="$(_idea_expand_path "$external" "$project")" || die 'Gradle 关联路径无法展开，无法确定当前项目'
        for key in distributionType gradleHome gradleJvm; do
            case "$(_idea_sync_count "$gradle" "$xpath[$index]/option[@name='$key']")" in 0|1) ;; *) die "Gradle 设置重复：$key" ;; esac
        done
        [ "$external" -ef "$project" ] || continue
        [ "$selected" -eq 0 ] || die '当前项目存在重复 Gradle 关联'
        selected="$index"
    done
    [ "$selected" -gt 0 ] || die 'IDEA 尚未关联所选 Gradle 项目，无法确定需同步的配置'
    IDEA_SYNC_GRADLE_INDEX="$selected"
}

_idea_sync_add_module() {
    local path="$1" project="$2" existing parent
    _idea_sync_safe_path "$path"
    [ -e "$path" ] || return 0
    parent="$(CDPATH= cd -- "$(dirname -- "$path")" && pwd -P)" || die '模块目录无法读取'
    path="$parent/${path##*/}"
    case "$path" in "$project"/*.iml) ;; *) die "项目引用了外部模块，请在 IDEA 中手动同步：$path" ;; esac
    for existing in ${IDEA_SYNC_MODULES[@]+"${IDEA_SYNC_MODULES[@]}"}; do [ "$existing" != "$path" ] || return 0; done
    _idea_sync_xml "$path" module
    case "$(_idea_sync_count "$path" '/module/component[@name="NewModuleRootManager"]')" in 0|1) ;; *) die '模块 NewModuleRootManager 重复' ;; esac
    IDEA_SYNC_MODULES+=("$path")
}

_idea_sync_modules() {
    local project="$1" file="$1/.idea/modules.xml" count index path url from_url entry
    if [ -e "$file" ] || [ -L "$file" ]; then
        _idea_sync_xml "$file" project
        _idea_sync_one "$file" '/project/component[@name="ProjectModuleManager"]' 'ProjectModuleManager'
        _idea_sync_one "$file" '/project/component[@name="ProjectModuleManager"]/modules' 'modules'
        count="$(_idea_sync_count "$file" '/project/component[@name="ProjectModuleManager"]/modules/module')"
        case "$count" in ''|*[!0-9]*) die '无法解析模块列表' ;; esac
        [ "$count" -le 1024 ] || die '模块列表过多'
        for ((index=1; index<=count; index++)); do
            entry="/project/component[@name='ProjectModuleManager']/modules/module[$index]"
            path="$(_idea_xml_value "$file" "$entry/@filepath")"
            url="$(_idea_xml_value "$file" "$entry/@fileurl")"
            from_url=''
            if [ -n "$url" ]; then
                case "$url" in file://*) from_url="${url#file://}" ;; *) die '模块 fileurl 不是本地文件引用' ;; esac
                from_url="$(_idea_expand_path "$from_url" "$project")" || die '模块 fileurl 无法展开'
            fi
            if [ -n "$path" ]; then
                path="$(_idea_expand_path "$path" "$project")" || die '模块 filepath 无法展开'
                if [ -n "$from_url" ] && [ "$path" != "$from_url" ] && ! [ "$path" -ef "$from_url" ]; then die '模块 filepath 与 fileurl 冲突'; fi
            else path="$from_url"; fi
            [ -n "$path" ] || die '模块文件引用缺失'
            _idea_sync_add_module "$path" "$project"
        done
    fi
    # 不用 process substitution：其中 find 的退出状态不会传播给调用者。
    find "$project" -name '*.iml' -print0 > "$IDEA_SYNC_WORK/modules.list" || die '模块文件扫描失败，未修改任何 IDEA 配置'
    while IFS= read -r -d '' path; do _idea_sync_add_module "$path" "$project"; done < "$IDEA_SYNC_WORK/modules.list"
}

_idea_sync_table() {
    local file="$1" project="$2" count index other name type home physical='' base candidate=0 canonical=0
    local names=() physical_homes=()
    IDEA_SYNC_KEEP_INDEX=0; IDEA_SYNC_MERGE=()
    if [ ! -e "$file" ] && [ ! -L "$file" ]; then
        _idea_sync_safe_path "$file"; _idea_sync_alias "$IDEA_SYNC_OLD_PROJECT_NAME"; return 0
    fi
    _idea_sync_xml "$file" application
    case "$(_idea_sync_count "$file" '/application/component[@name="ProjectJdkTable"]')" in 0|1) ;; *) die 'ProjectJdkTable 重复';; esac
    base='/application/component[@name="ProjectJdkTable"]/jdk'
    count="$(_idea_sync_count "$file" "$base")"
    case "$count" in ''|*[!0-9]*) die '无法解析 SDK 登记表' ;; esac
    [ "$count" -le 256 ] || die 'SDK 登记数量过多'
    for ((index=1; index<=count; index++)); do
        for type in name type homePath; do _idea_sync_one "$file" "$base[$index]/$type" "SDK $type"; done
        name="$(_idea_xml_value "$file" "$base[$index]/name/@value")"
        type="$(_idea_xml_value "$file" "$base[$index]/type/@value")"
        home="$(_idea_xml_value "$file" "$base[$index]/homePath/@value")"
        [ -n "$name" ] && [ -n "$type" ] && [ -n "$home" ] || die 'SDK 登记名称、类型或路径为空'
        case "$name" in *$'\n'*|*$'\r'*) die 'SDK 名称含换行，无法安全同步' ;; esac
        physical=''
        if [ "$type" = JavaSDK ]; then
            home="$(_idea_expand_path "$home" "$project")" || die 'Java SDK 路径无法展开'
            if [ -d "$home" ]; then physical="$(CDPATH= cd -- "$home" && pwd -P)" || die 'Java SDK 目录无法读取'; fi
        fi
        names+=("$name"); physical_homes+=("$physical")
        if [ "$name" = "$IDEA_JDK_NAME" ] && [ -n "$IDEA_SYNC_HOME" ]; then
            [ "$type" = JavaSDK ] && [ "$physical" = "$IDEA_SYNC_HOME" ] || die "SDK 名称冲突：$IDEA_JDK_NAME 已登记到其他 SDK 目录"
        fi
        for ((other=0; other<index-1; other++)); do
            [ "${names[$other]}" != "$name" ] || {
                if "$DRY_RUN" && [ -z "$IDEA_SYNC_HOME" ]; then
                    # 静态预检可确认同一物理 Java SDK；目标 JDK 验证与归并留给正式运行。
                    [ -n "$physical" ] && [ "${physical_homes[$other]}" = "$physical" ] || die "SDK 名称重复且路径不明确：$name"
                else
                    [ -n "$IDEA_SYNC_HOME" ] && [ "$physical" = "$IDEA_SYNC_HOME" ] && [ "${physical_homes[$other]}" = "$physical" ] || die "SDK 名称重复且路径不明确：$name"
                fi
            }
        done
        [ -n "$IDEA_SYNC_HOME" ] && [ "$type" = JavaSDK ] && [ "$physical" = "$IDEA_SYNC_HOME" ] || continue
        IDEA_SYNC_MERGE+=("$index"); _idea_sync_alias "$name"
        # 复用原始完整 roots；不得把可用登记替换成只含 homePath 的半成品。
        if [ "$(_idea_sync_count "$file" "$base[$index]/roots")" = 1 ] &&
           [ "$(_idea_sync_count "$file" "$base[$index]/roots/classPath/root[@type='composite']")" = 1 ] &&
           [ "$(_idea_sync_count "$file" "$base[$index]/roots/sourcePath/root[@type='composite']")" = 1 ] &&
           [ "$(_idea_sync_count "$file" "$base[$index]/roots/javadocPath/root[@type='composite']")" = 1 ] &&
           [ "$(_idea_sync_count "$file" "$base[$index]/roots/classPath/root/root[@url]")" -gt 0 ]; then
            [ "$candidate" -gt 0 ] || candidate="$index"
            if [ "$name" = "$IDEA_JDK_NAME" ] && [ "$canonical" -eq 0 ]; then canonical="$index"; fi
        fi
    done
    # 悬空的旧项目名称也需迁移；已登记的独立 SDK 留给模块原有设置。
    other=0
    for name in ${names[@]+"${names[@]}"}; do
        if [ "$name" = "$IDEA_SYNC_OLD_PROJECT_NAME" ]; then other=1; break; fi
    done
    if [ "$other" -eq 0 ]; then _idea_sync_alias "$IDEA_SYNC_OLD_PROJECT_NAME"; fi
    if [ "${#IDEA_SYNC_MERGE[@]}" -gt 0 ]; then
        [ "$candidate" -gt 0 ] || die '同目录 SDK 的 roots 不完整，请先在 IDEA 中修复 SDK 登记'
        if [ "$canonical" -gt 0 ]; then IDEA_SYNC_KEEP_INDEX="$canonical"; else IDEA_SYNC_KEEP_INDEX="$candidate"; fi
    fi
}

_idea_sync_new_sdk() {
    local home="$IDEA_SYNC_HOME" path escaped version="${PROBE_JDK_VERSION:-1.8}"
    [ -s "$home/jre/lib/rt.jar" ] && [ -s "$home/lib/tools.jar" ] || die 'JDK 8 缺少 rt.jar 或 tools.jar，无法生成完整 IDEA SDK roots'
    printf '<new><jdk version="2"><name value="%s"/><type value="JavaSDK"/><version value="java version &quot;%s&quot;"/><homePath value="%s"/><roots><annotationsPath><root type="composite"/></annotationsPath><classPath><root type="composite">' \
        "$(_idea_sync_escape "$IDEA_JDK_NAME")" "$(_idea_sync_escape "$version")" "$(_idea_sync_escape "$home")"
    for path in "$home"/jre/lib/*.jar "$home"/jre/lib/ext/*.jar "$home/lib/tools.jar"; do
        [ -s "$path" ] || continue
        printf '<root url="jar://%s!/" type="simple"/>' "$(_idea_sync_escape "$path")"
    done
    printf '</root></classPath><javadocPath><root type="composite"/></javadocPath><sourcePath><root type="composite">'
    if [ -s "$home/src.zip" ]; then printf '<root url="jar://%s/src.zip!/" type="simple"/>' "$(_idea_sync_escape "$home")"; fi
    printf '</root></sourcePath></roots><additional/></jdk></new>'
}

_idea_sync_prepare_file() {
    local target="$1" input="$1" index="${#IDEA_SYNC_TARGETS[@]}" output backup
    if [ ! -e "$target" ]; then
        input="$IDEA_SYNC_WORK/empty-table.xml"
    else
        # 当次快照独立于首次修改的历史 .bak，用于发布失败时完整恢复。
        cp -p "$target" "$IDEA_SYNC_WORK/original-$index.xml"
        input="$IDEA_SYNC_WORK/original-$index.xml"
        _idea_xml_valid "$input" || die "IDEA 配置在准备期间发生变化：$target"
    fi
    output="$IDEA_SYNC_WORK/output-$index.xml"
    xsltproc --nonet "$IDEA_SYNC_WORK/sync.xsl" "$input" > "$output" 2>/dev/null || die "IDEA XML 同步准备失败：$target"
    _idea_xml_valid "$output" || die "IDEA XML 同步结果无效：$target"
    if [ -e "$target" ]; then
        # 比较规范 XML 避免仅因序列化格式变化产生备份与 mtime 变化。
        xmllint --nonet --c14n "$input" > "$IDEA_SYNC_WORK/before-$index"
        xmllint --nonet --c14n "$output" > "$IDEA_SYNC_WORK/after-$index"
        cmp -s "$IDEA_SYNC_WORK/before-$index" "$IDEA_SYNC_WORK/after-$index" && return 0
    fi
    backup="$target.bak"
    _idea_sync_safe_path "$backup"
    [ ! -e "$backup" ] || [ -f "$backup" ] || die "IDEA 备份目标不是普通文件：$backup"
    IDEA_SYNC_TARGETS+=("$target"); IDEA_SYNC_OUTPUTS+=("$output")
}

_idea_sync_finish() {
    local status="$1" index path original rollback='' backup stage restore_failed=false
    # 清理不能覆盖原始错误状态，也不能让一次恢复失败中断其他文件的恢复。
    set +e
    if ! "$IDEA_SYNC_COMMITTED"; then
        for ((index=IDEA_SYNC_PUBLISHING-1; index>=0; index--)); do
            path="${IDEA_SYNC_TARGETS[$index]}"; original="$IDEA_SYNC_WORK/original-$index.xml"
            if [ -f "$original" ]; then
                # 失败的 rename 可能完全没有修改目标；保留其原有 mtime。
                if [ -f "$path" ] && cmp -s "$original" "$path"; then continue; fi
                rollback="$(mktemp "$(dirname -- "$path")/.idea-rollback.XXXXXXXX")"
                if [ -n "$rollback" ] && cp -p "$original" "$rollback" && mv -f "$rollback" "$path"; then
                    rollback=''
                else restore_failed=true; fi
                [ -z "$rollback" ] || rm -f "$rollback"
            else
                rm -f "$path" || restore_failed=true
            fi
        done
        for backup in ${IDEA_SYNC_NEW_BACKUPS[@]+"${IDEA_SYNC_NEW_BACKUPS[@]}"}; do rm -f "$backup" || restore_failed=true; done
        if "$restore_failed"; then
            log "[IDEA 配置恢复失败] 当次原件保留在：$IDEA_SYNC_WORK"
        elif [ "$IDEA_SYNC_PUBLISHING" -gt 0 ]; then
            log '[IDEA 配置已恢复] 发布失败，已恢复本次运行之前的配置。'
        fi
    fi
    for stage in ${IDEA_SYNC_STAGED[@]+"${IDEA_SYNC_STAGED[@]}"}; do rm -f "$stage"; done
    if ! "$restore_failed"; then rm -rf "$IDEA_SYNC_WORK"; fi
    return "$status"
}

idea_sdk_sync() {
    local project="$1" misc gradle table value path index stage before
    local IDEA_SYNC_HOME='' IDEA_SYNC_WORK='' IDEA_SYNC_GRADLE_INDEX=0 IDEA_SYNC_KEEP_INDEX=0 IDEA_SYNC_OLD_PROJECT_NAME=''
    local IDEA_SYNC_PUBLISHING=0 IDEA_SYNC_COMMITTED=false
    local IDEA_SYNC_ALIASES=() IDEA_SYNC_MODULES=() IDEA_SYNC_MERGE=() IDEA_SYNC_TARGETS=() IDEA_SYNC_OUTPUTS=() IDEA_SYNC_STAGED=() IDEA_SYNC_NEW_BACKUPS=()
    require_command xmllint; require_command xsltproc
    case "$IDEA_JDK_NAME" in ''|*$'\n'*|*$'\r'*) die 'IDEA_JDK_NAME 不支持空值或换行' ;; esac
    case "$project" in /*) ;; *) project="$(pwd -P)/$project" ;; esac
    _idea_sync_safe_path "$project"
    [ -d "$project" ] || die "项目目录不存在：$project"
    project="$(CDPATH= cd -- "$project" && pwd -P)"
    misc="$project/.idea/misc.xml"; gradle="$project/.idea/gradle.xml"
    _idea_sync_safe_path "$misc"; _idea_sync_safe_path "$gradle"
    if [ ! -e "$misc" ] && [ ! -e "$gradle" ]; then
        log '[IDEA 项目待配置] 尚未在 IDEA 中导入项目；请先导入并选择 Gradle 分发方式，再运行 SDK 同步。'
        return 2
    fi
    _idea_sync_stopped
    _idea_sync_project "$project" "$misc" "$gradle"
    IDEA_SYNC_WORK="$(mktemp -d "${TMPDIR:-/tmp}/team-idea-sdk.XXXXXXXX")"
    trap '_idea_sync_finish "$?"' EXIT
    trap 'exit 130' INT; trap 'exit 143' TERM
    _idea_sync_modules "$project"
    require_absolute_path IDEA_CONFIG_DIR "$IDEA_CONFIG_DIR"
    table="$IDEA_CONFIG_DIR/options/jdk.table.xml"
    _idea_sync_safe_path "$table"
    if ! "$DRY_RUN"; then
        probe_jdk8
        [ -n "$PROBE_JDK_HOME" ] || die '没有可用的 JDK 8，请先配置 JDK 8 再同步 IDEA SDK'
        IDEA_SYNC_HOME="$(CDPATH= cd -- "$PROBE_JDK_HOME" && pwd -P)"
    fi
    _idea_sync_table "$table" "$project"
    if "$DRY_RUN"; then
        log "[预演] 将项目 SDK 与当前项目 Gradle JVM 同步为：$IDEA_JDK_NAME"
        log '[预演] JDK 目录与名称冲突待正式运行验证：由 probe_jdk8 选择可用 JDK 8，再合并同目录别名与模块引用。'
        log '[预演] 未执行 JDK，未写入配置或备份；Gradle 分发方式与其他关联保持。'
        IDEA_SYNC_COMMITTED=true
        _idea_sync_finish 0
        trap - EXIT INT TERM
        return 0
    fi
    cp "$REPO_ROOT/scripts/lib/idea-sdk-sync.xsl" "$IDEA_SYNC_WORK/sync.xsl"
    printf '<application><component name="ProjectJdkTable"/></application>' > "$IDEA_SYNC_WORK/empty-table.xml"
    {
        printf '<plan name="%s" home="%s" keep-index="%s" gradle-index="%s">' "$(_idea_sync_escape "$IDEA_JDK_NAME")" "$(_idea_sync_escape "$IDEA_SYNC_HOME")" "$IDEA_SYNC_KEEP_INDEX" "$IDEA_SYNC_GRADLE_INDEX"
        for value in ${IDEA_SYNC_ALIASES[@]+"${IDEA_SYNC_ALIASES[@]}"}; do printf '<alias name="%s"/>' "$(_idea_sync_escape "$value")"; done
        for index in ${IDEA_SYNC_MERGE[@]+"${IDEA_SYNC_MERGE[@]}"}; do printf '<merge index="%s"/>' "$index"; done
        if [ "$IDEA_SYNC_KEEP_INDEX" -eq 0 ]; then _idea_sync_new_sdk; fi
        printf '</plan>'
    } > "$IDEA_SYNC_WORK/plan.xml"
    _idea_xml_valid "$IDEA_SYNC_WORK/plan.xml" || die 'SDK 同步计划不是有效 XML'
    _idea_sync_prepare_file "$table"; _idea_sync_prepare_file "$misc"; _idea_sync_prepare_file "$gradle"
    for path in ${IDEA_SYNC_MODULES[@]+"${IDEA_SYNC_MODULES[@]}"}; do _idea_sync_prepare_file "$path"; done
    # 全部预检结束；先在目标文件系统准备结果和备份，再以 rename 发布。
    _idea_sync_stopped
    for ((index=0; index<${#IDEA_SYNC_TARGETS[@]}; index++)); do
        path="${IDEA_SYNC_TARGETS[$index]}"
        _idea_sync_safe_path "$path"; _idea_sync_safe_path "$path.bak"
        mkdir -p "$(dirname -- "$path")"
        stage="$(mktemp "$(dirname -- "$path")/.idea-sdk.XXXXXXXX")"
        IDEA_SYNC_STAGED+=("$stage")
        if [ -e "$path" ]; then cp -p "$path" "$stage"; fi
        cat "${IDEA_SYNC_OUTPUTS[$index]}" > "$stage"
    done
    _idea_sync_stopped
    for ((index=0; index<${#IDEA_SYNC_TARGETS[@]}; index++)); do
        path="${IDEA_SYNC_TARGETS[$index]}"
        if [ -f "$IDEA_SYNC_WORK/original-$index.xml" ]; then
            cmp -s "$IDEA_SYNC_WORK/original-$index.xml" "$path" || die "IDEA 配置在准备期间发生变化，未发布：$path"
        elif [ -e "$path" ] || [ -L "$path" ]; then die "IDEA 配置在准备期间被创建，未发布：$path"; fi
    done
    for ((index=0; index<${#IDEA_SYNC_TARGETS[@]}; index++)); do
        path="${IDEA_SYNC_TARGETS[$index]}"
        if [ -f "$IDEA_SYNC_WORK/original-$index.xml" ] && [ ! -e "$path.bak" ]; then
            IDEA_SYNC_NEW_BACKUPS+=("$path.bak")
            cp -p "$IDEA_SYNC_WORK/original-$index.xml" "$path.bak"
        fi
    done
    for ((index=0; index<${#IDEA_SYNC_TARGETS[@]}; index++)); do
        IDEA_SYNC_PUBLISHING=$((index + 1))
        mv -f "${IDEA_SYNC_STAGED[$index]}" "${IDEA_SYNC_TARGETS[$index]}"
    done
    IDEA_SYNC_COMMITTED=true
    _idea_sync_finish 0
    trap - EXIT INT TERM
    log "[IDEA SDK 已同步] Project SDK=$IDEA_JDK_NAME；Gradle JVM=$IDEA_JDK_NAME；JDK 8=$IDEA_SYNC_HOME"
    log '[IDEA 同步待确认] 请打开 IDEA 并执行 Reload All Gradle Projects；配置写入不代表 IDE 已重新加载。'
}
