#!/bin/bash
# 修复审计只记录本工具管理的配置；目录私有，报告不输出配置文件的无关内容。
audit_field() {
    local value="$1"
    value="${value//$'\t'/ }"; value="${value//$'\n'/ }"; value="${value//$'\r'/ }"
    printf '%s' "$value"
}

audit_begin() {
    AUDIT_SCOPE="$1"; AUDIT_PROJECT="${2:-}"
    local history="${REPAIR_HISTORY_DIR:-$HOME/Library/Logs/team-java-env/history}" module index=0
    require_absolute_path REPAIR_HISTORY_DIR "$history"
    [ ! -L "$history" ] || die '历史目录不能是符号链接'
    (umask 077; mkdir -p "$history") || die '无法创建修复历史目录'
    REPAIR_RUN_DIR="$(umask 077; mktemp -d "$history/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")" || die '无法建立本次历史记录'
    export REPAIR_RUN_DIR
    AUDIT_STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    AUDIT_PROFILE="${SHELL_PROFILE:-}"
    if [ -z "$AUDIT_PROFILE" ]; then
        case "${SHELL:-/bin/zsh}" in */bash) AUDIT_PROFILE="$HOME/.bash_profile" ;; *) AUDIT_PROFILE="$HOME/.zshrc" ;; esac
    fi
    AUDIT_KEYS=(environment jdk-environment gradle-environment shell-profile)
    AUDIT_PATHS=("$ENV_FILE" "${JDK_ENV_FILE:-${ENV_FILE%/*}/jdk.sh}" "${GRADLE_ENV_FILE:-${ENV_FILE%/*}/gradle.sh}" "$AUDIT_PROFILE")
    printf 'step\tstatus\texit_code\tlog\n' > "$REPAIR_RUN_DIR/steps.tsv"
    printf 'status\texit_code\tscope\tproject\nRUNNING\t-\t%s\t%s\n' "$AUDIT_SCOPE" "$(audit_field "$AUDIT_PROJECT")" > "$REPAIR_RUN_DIR/result.tsv"
    mkdir "$REPAIR_RUN_DIR/logs"
    if [ -n "$AUDIT_PROJECT" ]; then
        AUDIT_KEYS+=(wrapper-properties)
        AUDIT_PATHS+=("$AUDIT_PROJECT/gradle/wrapper/gradle-wrapper.properties")
        case "$AUDIT_SCOPE" in
            all|jdk|gradle|idea)
                AUDIT_KEYS+=(idea-sdk-table idea-project-sdk idea-gradle-jvm)
                AUDIT_PATHS+=("$IDEA_CONFIG_DIR/options/jdk.table.xml" "$AUDIT_PROJECT/.idea/misc.xml" "$AUDIT_PROJECT/.idea/gradle.xml")
                # find 默认不进入符号链接目录；保留现有模块文件的私有快照。
                find "$AUDIT_PROJECT" -name '*.iml' -print0 > "$REPAIR_RUN_DIR/module-paths.tmp" || return 1
                while IFS= read -r -d '' module; do
                    [ -f "$module" ] || [ -L "$module" ] || continue
                    index=$((index + 1))
                    AUDIT_KEYS+=("idea-module-$(printf '%04d' "$index")")
                    AUDIT_PATHS+=("$module")
                done < "$REPAIR_RUN_DIR/module-paths.tmp"
                rm -f "$REPAIR_RUN_DIR/module-paths.tmp" || return 1 ;;
        esac
    fi
    audit_snapshot before
}

audit_snapshot() {
    local phase="$1" index path key kind hash
    mkdir -p "$REPAIR_RUN_DIR/$phase" || return 1
    printf 'key\tpath\ttype\tsha256\n' > "$REPAIR_RUN_DIR/${phase}-files.tsv" || return 1
    for ((index=0; index<${#AUDIT_PATHS[@]}; index++)); do
        path="${AUDIT_PATHS[$index]}"; key="${AUDIT_KEYS[$index]}"; kind=missing; hash='-'
        if [ -f "$path" ]; then
            kind=file
            [ ! -L "$path" ] || kind=symlink-file
            cat "$path" > "$REPAIR_RUN_DIR/$phase/$key" || return 1
            chmod 600 "$REPAIR_RUN_DIR/$phase/$key" || return 1
            hash="$(shasum -a 256 < "$REPAIR_RUN_DIR/$phase/$key")" || return 1
            hash="${hash%% *}"
        elif [ -e "$path" ] || [ -L "$path" ]; then
            kind=other
        fi
        printf '%s\t%s\t%s\t%s\n' "$key" "$(audit_field "$path")" "$kind" "$hash" >> "$REPAIR_RUN_DIR/${phase}-files.tsv" || return 1
    done
}

audit_step() {
    printf '%s\t%s\t%s\t%s\n' "$(audit_field "$1")" "$2" "$3" "$(audit_field "$4")" >> "$REPAIR_RUN_DIR/steps.tsv"
}

audit_set_result() {
    printf 'status\texit_code\tscope\tproject\n%s\t%s\t%s\t%s\n' "$1" "$2" "$AUDIT_SCOPE" "$(audit_field "$AUDIT_PROJECT")" > "$REPAIR_RUN_DIR/result.tsv.tmp" || return 1
    mv "$REPAIR_RUN_DIR/result.tsv.tmp" "$REPAIR_RUN_DIR/result.tsv" || return 1
}

audit_record_failure() {
    audit_set_result FAILED "$1" || true
    # 覆盖可能未完成的报告，不留下拟成功状态；已有快照和日志继续保留。
    printf '# 环境修复记录\n\n- 最终状态：**FAILED**\n- 退出码：%s\n\n修复或审计保存未完成。请检查 result.tsv、steps.tsv、logs/ 和已有配置快照。\n' "$1" > "$REPAIR_RUN_DIR/report.md" || return 1
}

audit_xml_field() {
    local value
    value="$(xmllint --nonet --xpath "string($2)" "$1" 2>/dev/null)" || return 1
    printf '%s=%s\n' "$3" "$(audit_field "$value")"
}

audit_xml_review() {
    local file="$1" key="$2" base count index
    [ "$file" != /dev/null ] || return 0
    # 与项目预检和改写共用解码后检查；错误只输出固定说明。
    if ! safe_xml_valid "$file"; then
        printf '%s\n' 'XML 无法安全解析；相关字段摘要不可用。'
        return 0
    fi
    case "$key" in
        idea-sdk-table) base='/application/component[@name="ProjectJdkTable"]/jdk' ;;
        idea-project-sdk) base='/project/component[@name="ProjectRootManager"]' ;;
        idea-gradle-jvm) base='/project/component[@name="GradleSettings"]/option[@name="linkedExternalProjectsSettings"]/GradleProjectSettings' ;;
        idea-module-*) base='/module/component[@name="NewModuleRootManager"]/orderEntry[@type="jdk"]' ;;
        *) return 1 ;;
    esac
    count="$(xmllint --nonet --xpath "count($base)" "$file" 2>/dev/null)" || return 1
    case "$count" in ''|*[!0-9]*) return 1 ;; esac
    if [ "$count" -gt 256 ]; then
        printf '%s\n' 'XML 相关设置过多；相关字段摘要不可用。'
        return 0
    fi
    for ((index=1; index<=count; index++)); do
        case "$key" in
            idea-sdk-table)
                audit_xml_field "$file" "($base)[$index]/name/@value" "SDK[$index].name" || return 1
                audit_xml_field "$file" "($base)[$index]/homePath/@value" "SDK[$index].home" || return 1
                audit_xml_field "$file" "($base)[$index]/type/@value" "SDK[$index].type" || return 1 ;;
            idea-project-sdk)
                audit_xml_field "$file" "($base)[$index]/@project-jdk-name" "Project[$index].SDK" || return 1
                audit_xml_field "$file" "($base)[$index]/@project-jdk-type" "Project[$index].SDKType" || return 1 ;;
            idea-gradle-jvm)
                audit_xml_field "$file" "($base)[$index]/option[@name='gradleJvm']/@value" "Gradle[$index].gradleJvm" || return 1 ;;
            idea-module-*)
                audit_xml_field "$file" "($base)[$index]/@jdkName" "Module[$index].jdkName" || return 1
                audit_xml_field "$file" "($base)[$index]/@jdkType" "Module[$index].jdkType" || return 1 ;;
        esac
    done
}

audit_review_content() {
    case "${2:-}" in idea-*) audit_xml_review "$1" "$2"; return ;; esac
    # 原始配置留在私有备份里；可分享差异只展示工具管理区块。
    # 不对完整配置做 diff，避免末尾换行修复把原有个人令牌带进报告。
    awk '
        $0 == "# >>> team-java-env managed >>>" {if (inside) bad=1; inside=1}
        inside {buffer=buffer $0 "\n"}
        $0 == "# <<< team-java-env managed <<<" {if (!inside) bad=1; inside=0}
        END {if (inside || bad) exit 1; printf "%s", buffer}
    ' "$1"
}

audit_finish() {
    local status="$1" code="$2" index path key before after changes=0
    audit_snapshot after || return 1
    : > "$REPAIR_RUN_DIR/config-changes.diff" || return 1
    {
        printf '# 环境修复记录\n\n- 开始时间（UTC）：%s\n- 结束时间（UTC）：%s\n- 范围：%s\n- 项目：%s\n- 最终状态：**%s**\n- 退出码：%s\n\n' \
            "$AUDIT_STARTED" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$AUDIT_SCOPE" "${AUDIT_PROJECT:-未选择项目}" "$status" "$code"
        printf '## 步骤与验证\n\n| 步骤 | 状态 | 退出码 | 日志 |\n| --- | --- | --- | --- |\n'
        while IFS=$'\t' read -r step result rc logfile; do
            [ "$step" != step ] || continue
            printf '| %s | %s | %s | %s |\n' "$step" "$result" "$rc" "$logfile"
        done < "$REPAIR_RUN_DIR/steps.tsv"
        printf '\n## 配置修改清单\n\n'
        for ((index=0; index<${#AUDIT_PATHS[@]}; index++)); do
            path="${AUDIT_PATHS[$index]}"; key="${AUDIT_KEYS[$index]}"
            before="$REPAIR_RUN_DIR/before/$key"; after="$REPAIR_RUN_DIR/after/$key"
            if [ -f "$before" ] && [ -f "$after" ] && cmp -s "$before" "$after"; then continue; fi
            if [ ! -f "$before" ] && [ ! -f "$after" ]; then continue; fi
            changes=$((changes + 1))
            printf -- '- `%s`：' "$path"
            if [ ! -f "$before" ]; then printf '新增\n'; before=/dev/null
            elif [ ! -f "$after" ]; then printf '移除\n'; after=/dev/null
            else printf '修改；原文件备份：`before/%s`\n' "$key"; fi
            audit_review_content "$before" "$key" > "$REPAIR_RUN_DIR/before-review.tmp" || return 1
            audit_review_content "$after" "$key" > "$REPAIR_RUN_DIR/after-review.tmp" || return 1
            diff -U0 --label "before/$key (managed fields)" --label "after/$key (managed fields)" \
                "$REPAIR_RUN_DIR/before-review.tmp" "$REPAIR_RUN_DIR/after-review.tmp" >> "$REPAIR_RUN_DIR/config-changes.diff" || [ "$?" -eq 1 ] || return 1
        done
        [ "$changes" -ne 0 ] || printf '受管配置未发生变化，已复用现有设置。\n'
        printf '\n工具管理区块和 IDEA SDK 相关字段差异见 `config-changes.diff`（零行上下文）；前后摘要见 `before-files.tsv`、`after-files.tsv`。XML 仅展示 SDK 名称、目录、类型以及项目和模块 SDK、Gradle JVM 引用。完整文件变化可在本机比较私有备份，不将其他个人配置复制到差异报告。\n'
        printf '\n## 安装与项目构建\n\n安装路径、复用或失败信息见各步骤日志；插件安装结果见 `plugins-result.tsv`，最终验证见 `plugins-verification.tsv`（若执行该阶段）。插件备份在本次记录的 `plugin-backups/` 下。\n'
        printf '\n项目构建由独立步骤记录；只有成功退出并确认构建成功才标为通过。未选择项目时不宣称构建通过。构建可能生成项目 build/ 与 Gradle 缓存。\n'
        printf '\n这些备份仅供本机review；共享时优先提供本报告与必要步骤日志，原始配置备份可能含个人配置。\n'
    } > "$REPAIR_RUN_DIR/report.md.tmp" || return 1
    rm -f "$REPAIR_RUN_DIR/before-review.tmp" "$REPAIR_RUN_DIR/after-review.tmp" || return 1
    [ ! -e "$REPAIR_RUN_DIR/report.md" ] || [ -f "$REPAIR_RUN_DIR/report.md" ] || return 1
    mv "$REPAIR_RUN_DIR/report.md.tmp" "$REPAIR_RUN_DIR/report.md" || return 1
    audit_set_result "$status" "$code" || return 1
    printf '\n修复历史：%s\n变更总结：%s/report.md\n配置差异：%s/config-changes.diff\n' "$REPAIR_RUN_DIR" "$REPAIR_RUN_DIR" "$REPAIR_RUN_DIR"
}
