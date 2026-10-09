#!/bin/bash
# 单一组件计划及执行队列；成员只依赖 macOS 自带 Bash。
set -uo pipefail
source "$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/lib" && pwd)/common.sh"
components='' gradle_version=4.5.1 node_version=14
gradle_set=false node_set=false preview=false plan_only=false expected_plan=''
usage_error() { printf '用法错误：%s\n' "$*" >&2; exit 2; }
usage() {
    printf '%s\n' '用法：install --components jdk,gradle,nvm,iterm2,oh-my-zsh,idea|all' \
        '  --gradle-version 4.5.1|6.8|all' '  --node-version none|10|14|18|22|all' \
        '  --dry-run  只读预演；--plan-json 输出结构化计划。'
}
for argument in "$@"; do [ "$argument" != --plain ] || usage_error '--plain 已删除，请使用交互终端或明确组件。'; done
while [ "$#" -gt 0 ]; do
    case "$1" in
        --components|--gradle-version|--node-version|--expected-plan)
            [ "$#" -ge 2 ] && [ -n "$2" ] || usage_error "$1 缺少值"
            case "$1" in
                --components) components="$2" ;;
                --gradle-version) gradle_version="$2"; gradle_set=true ;;
                --node-version) node_version="$2"; node_set=true ;;
                --expected-plan) expected_plan="$2" ;;
            esac
            shift 2 ;;
        --dry-run) preview=true; shift ;;
        --plan-json) plan_only=true; shift ;;
        --help|-h) usage; exit 0 ;;
        *) usage_error "未知参数：$1" ;;
    esac
done
if [ -z "$components" ]; then
    if "$preview" || "$plan_only"; then components=all
    else usage_error '请用 --components 明确选择组件。'; fi
fi
case "$components" in ,*|*,|*,,*) usage_error '组件列表包含空项' ;; esac
case "$gradle_version" in 4.5.1|6.8|all) ;; *) usage_error 'Gradle 仅支持 4.5.1、6.8 或 all' ;; esac
case "$node_version" in none|10|14|18|22|all) ;; *) usage_error 'Node 仅支持 none、10、14、18、22 或 all' ;; esac
selected=','
if [ "$components" = all ]; then selected=',jdk,gradle,nvm,iterm2,oh-my-zsh,idea,'
else
    remaining="$components"
    while :; do
        part="${remaining%%,*}"
        case "$part" in jdk|gradle|nvm|iterm2|oh-my-zsh|idea) ;; *) usage_error "未知组件：$part" ;; esac
        case "$selected" in *",$part,"*) ;; *) selected="$selected$part," ;; esac
        [ "$remaining" != "$part" ] || break
        remaining="${remaining#*,}"
    done
fi
has_component() { case "$selected" in *",$1,"*) return 0 ;; *) return 1 ;; esac; }
if "$gradle_set" && ! has_component gradle; then usage_error '未选择 Gradle，不能指定其版本'; fi
if "$node_set" && ! has_component nvm; then usage_error '未选择 nvm，不能指定 Node 版本'; fi
if has_component gradle && ! has_component jdk; then selected="${selected}jdk,"; fi
gradle_default="$gradle_version"
if [ "$gradle_version" = all ]; then
    gradle_default=4.5.1
    if [ -f "$GRADLE_DEFAULT_FILE" ] && [ ! -L "$GRADLE_DEFAULT_FILE" ]; then
        saved="$(cat "$GRADLE_DEFAULT_FILE")"
        case "$saved" in 4.5.1|6.8) gradle_default="$saved" ;; esac
    fi
fi
component_title() {
    case "$1" in jdk) printf 'JDK 8';; gradle) printf 'Gradle';; nvm) printf 'nvm / Node';;
        iterm2) printf 'iTerm2';; oh-my-zsh) printf 'Oh My Zsh';; idea) printf 'IDEA / 插件';; esac
}
source "$REPO_ROOT/scripts/lib/frontend.sh"
marker_ownership() {
    local marker="$1" kind="$2"
    if [ ! -e "$marker" ] && [ ! -L "$marker" ]; then printf '外部安装'; return 0; fi
    if [ -f "$marker" ] && [ ! -L "$marker" ] &&
        [ "$(plutil -extract schema raw -o - "$marker" 2>/dev/null)" = 1 ] &&
        [ "$(plutil -extract kind raw -o - "$marker" 2>/dev/null)" = "$kind" ]; then
        case "$(plutil -extract tool raw -o - "$marker" 2>/dev/null)" in
            team-java-env|team-frontend-env) printf '受本工具管理'; return 0 ;; esac
    fi
    printf '来源未知'
}
component_metadata() {
    local component="$1" marker='' probe_target='' candidate saved='' marker_kind="$1" source_seen='' current_source=''
    status='待安装'; ownership='尚未安装'; before=''; after=''; impact=''; validation='pending'
    case "$component" in
        jdk) target="$JDK_INSTALL_DIR"; version=8; marker="$target/.team-java-env-install.json" ;;
        gradle)
            target="$HOME/.local/share/java-dev"; version="$gradle_version"
            for candidate in 4.5.1 6.8; do
                [ "$gradle_version" = all ] || [ "$candidate" = "$gradle_version" ] || continue
                probe_target="$target/gradle-$candidate"
                if [ -e "$probe_target" ] || [ -L "$probe_target" ]; then
                    [ "$status" = '目标冲突' ] || status='已存在，待验证'
                    current_source="$(marker_ownership "$probe_target/.team-java-env-install.json" gradle)"
                    if [ -z "$source_seen" ]; then source_seen="$current_source"; ownership="$current_source"
                    elif [ "$source_seen" != "$current_source" ]; then ownership='混合来源，待核验'; fi
                    [ -d "$probe_target" ] && [ ! -L "$probe_target" ] || status='目标冲突'
                fi
            done
            if [ -f "$GRADLE_DEFAULT_FILE" ] && [ ! -L "$GRADLE_DEFAULT_FILE" ]; then before="$(cat "$GRADLE_DEFAULT_FILE")"; fi
            after="$before"
            if has_component gradle; then
                after="$gradle_default"
                if [ "$before" = "$after" ]; then impact="默认保留 ${before:-未设置}"
                else impact="新终端默认 ${before:-未设置} → $after"; fi
            fi ;;
        nvm)
            target="${NVM_DIR:-$HOME/.nvm}"; version="$node_version"; marker="$target/.team-frontend-env-install.json"
            NVM_DIR="$target" frontend_node_default_plan "$node_version" static
            before="$FRONTEND_DEFAULT_BEFORE"; after="$before"; validation="$FRONTEND_DEFAULT_VALIDATION"
            if has_component nvm; then after="$FRONTEND_DEFAULT_AFTER"; impact="$FRONTEND_DEFAULT_IMPACT"; fi ;;
        iterm2)
            target="$USER_APPLICATIONS_DIR/iTerm.app"; version='已锁定'
            for candidate in "$HOME/.local/share/team-frontend-env/receipts"/iterm2-*/.team-frontend-env-install.json; do
                [ -f "$candidate" ] && [ ! -L "$candidate" ] || continue
                [ "$(plutil -extract app_path raw -o - "$candidate" 2>/dev/null)" = "$target" ] || continue
                marker="$candidate"; break
            done ;;
        oh-my-zsh) target="${ZSH:-$HOME/.oh-my-zsh}"; version='已锁定'; marker="$target/.team-frontend-env-install.json" ;;
        idea) target="$IDEA_APP"; version="$IDEA_VERSION"; marker="$target/.team-java-env-install.json" ;;
    esac
    if [ "$component" != gradle ] && { [ -e "$target" ] || [ -L "$target" ]; }; then
        status='已存在，待验证'; ownership='外部安装'
        [ -d "$target" ] && [ ! -L "$target" ] || status='目标冲突'
    fi
    if [ -n "$marker" ] && { [ -e "$marker" ] || [ -L "$marker" ]; }; then
        ownership="$(marker_ownership "$marker" "$marker_kind")"
    fi
}
emit_component() {
    local component="$1" key value
    component_metadata "$component"
    printf '{"id":"%s","title":' "$component"; json_quote "$(component_title "$component")"
    for key in version target status ownership default_before default_after default_impact default_validation; do
        case "$key" in version) value="$version" ;; target) value="$target" ;; status) value="$status" ;; ownership) value="$ownership" ;;
            default_before) value="$before" ;; default_after) value="$after" ;; default_impact) value="$impact" ;; default_validation) value="$validation" ;; esac
        printf ',"%s":' "$key"; json_quote "$value"
    done
    printf '}'
}
make_plan() {
    local component separator=''
    printf '{"schema":1,"gradle_version":"%s","gradle_default":"%s","node_version":"%s","components":[' "$gradle_version" "$gradle_default" "$node_version"
    for component in jdk gradle nvm iterm2 oh-my-zsh idea; do
        has_component "$component" || continue
        printf '%s' "$separator"; emit_component "$component"; separator=','
    done
    printf '],"inventory":['; separator=''
    for component in jdk gradle nvm iterm2 oh-my-zsh idea; do
        printf '%s' "$separator"; emit_component "$component"; separator=','
    done
    printf ']}\n'
}
plan="$(make_plan)"
if "$plan_only"; then printf '%s\n' "$plan"; exit 0; fi
if [ -n "$expected_plan" ]; then
    actual="$(printf '%s' "$plan" | /usr/bin/shasum -a 256)"; actual="${actual%% *}"
    [ "$actual" = "$expected_plan" ] || { printf '安装范围已变化，请返回选择页重新选择。\n' >&2; exit 2; }
fi
invoke() { /bin/bash "$REPO_ROOT/scripts/$1" "${@:2}"; }
component_run() {
    local id="$1" dry="$2" version result=0
    local options=()
    [ "$dry" != true ] || options=(--dry-run)
    case "$id" in
        jdk) invoke runtime/config-jdk.sh ${options[@]+"${options[@]}"} ;;
        gradle)
            for version in 4.5.1 6.8; do
                [ "$gradle_version" = all ] || [ "$version" = "$gradle_version" ] || continue
                GRADLE_VERSION="$version" GRADLE_REGISTER_ONLY=1 GRADLE_INSTALL_DIR="$HOME/.local/share/java-dev/gradle-$version" \
                    invoke runtime/install-gradle.sh ${options[@]+"${options[@]}"} || result=$?
                [ "$result" -eq 0 ] || return "$result"
            done
            if [ "$dry" != true ]; then
                (source "$ENV_FILE"; gradle_use "$gradle_default" --default) || return $?
                printf '新开终端，或先执行：source %s\n' "$(shell_quote "$ENV_FILE")"
                printf '查看版本：gradle_use --list\n'
                for version in 4.5.1 6.8; do
                    [ "$gradle_version" = all ] || [ "$version" = "$gradle_version" ] || continue
                    printf '当前终端切换：gradle_use %s；设为新终端默认：gradle_use %s --default\n' "$version" "$version"
                done
            fi ;;
        nvm) invoke runtime/install-node.sh --version "$node_version" ${options[@]+"${options[@]}"} ;;
        iterm2) invoke software/install-iterm2.sh ${options[@]+"${options[@]}"} ;;
        oh-my-zsh) invoke software/install-zsh.sh ${options[@]+"${options[@]}"} ;;
        idea)
            invoke download-tools.sh --install-idea ${options[@]+"${options[@]}"} || return $?
            if [ "$dry" = true ] && [ ! -d "$IDEA_APP" ]; then
                printf '[预演] 安装 IDEA 后核验并安装六个推荐插件。\n'
            else invoke software/install-idea-plugins.sh ${options[@]+"${options[@]}"} || return $?; fi
            invoke runtime/config-idea-sdk.sh --global ${options[@]+"${options[@]}"}
            result=$?
            if [ "$result" -eq 2 ] && ! has_component jdk; then return 0; fi
            return "$result" ;;
    esac
}
# 先完成全计划只读预检；任何预检失败都不能产生部分安装。
for component in jdk gradle nvm iterm2 oh-my-zsh idea; do
    has_component "$component" || continue
    component_run "$component" true || exit $?
done
if "$preview"; then printf '预演结束，未执行安装或项目构建。\n'; exit 0; fi
if has_component jdk; then invoke runtime/config-jdk.sh --check-only || exit $?; fi
if has_component gradle; then
    for version in 4.5.1 6.8; do
        [ "$gradle_version" = all ] || [ "$version" = "$gradle_version" ] || continue
        GRADLE_JDK_PLANNED=1 GRADLE_VERSION="$version" GRADLE_INSTALL_DIR="$HOME/.local/share/java-dev/gradle-$version" \
            invoke runtime/install-gradle.sh --check-only || exit $?
    done
fi
if has_component nvm; then invoke runtime/install-node.sh --version "$node_version" --check-only || exit $?; fi
if has_component iterm2; then invoke software/install-iterm2.sh --check-only || exit $?; fi
if has_component oh-my-zsh; then invoke software/install-zsh.sh --check-only || exit $?; fi
source "$REPO_ROOT/scripts/lib/frontend.sh"
report_root="$HOME/Library/Logs/team-java-env/components"
frontend_check_directory "$report_root"
(umask 077; mkdir -p "$report_root") || exit 1
run_dir="$(umask 077; mktemp -d "$report_root/$(date +%Y%m%d-%H%M%S)-XXXXXXXX")" || exit 1
printf '%s\n' "$plan" > "$run_dir/plan.json" || exit 1
printf 'component\tstatus\texit_code\tlog\treason\n' > "$run_dir/steps.tsv" || exit 1
finished_components=',' current_component=''
record_component() {
    local id="$1" state="$2" code="$3" logfile="$4" reason="${5:-}" event_title
    event_title="$(component_title "$id")"
    [ -z "$reason" ] || event_title="${event_title}：$reason"
    printf '%s\t%s\t%s\t%s\t%s\n' "$id" "$state" "$code" "$logfile" "$reason" >> "$run_dir/steps.tsv"
    finished_components="$finished_components$id,"
    [ "${TEAM_TUI_EVENTS:-0}" != 1 ] || printf '@@TEAM_TUI\tcomponent\t%s\t%s\t%s\n' "$id" "$state" "$event_title"
}
finish_report() {
    result=$?; trap - EXIT
    local id state reason
    case "$result" in 129|130|143) state=cancelled; reason='已取消，未执行' ;; *) state=failed; reason='任务结束，未执行' ;; esac
    for id in jdk gradle nvm iterm2 oh-my-zsh idea; do
        has_component "$id" || continue
        case "$finished_components" in *",$id,"*) continue ;; esac
        if [ "$id" = "$current_component" ]; then record_component "$id" "$state" "$result" "$id.log"
        else record_component "$id" skipped "$result" - "$reason"; fi
    done
    final=FAILED
    case "$result" in 0) final=SUCCEEDED ;; 129|130|143) final=CANCELLED ;; esac
    printf 'status\texit_code\n%s\t%s\n' "$final" "$result" > "$run_dir/result.tsv" || result=1
    printf '本次安装记录：%s\n' "$run_dir"
    exit "$result"
}
trap finish_report EXIT
count=0
for component in jdk gradle nvm iterm2 oh-my-zsh idea; do has_component "$component" && count=$((count + 1)); done
[ "${TEAM_TUI_EVENTS:-0}" != 1 ] || printf '@@TEAM_TUI\tplan\tcomponents\t%s\t安装计划\n' "$count"
if [ "${TEAM_TUI_EVENTS:-0}" = 1 ]; then
    for component in jdk gradle nvm iterm2 oh-my-zsh idea; do
        has_component "$component" || continue
        printf '@@TEAM_TUI\tcomponent\t%s\tpending\t%s\n' "$component" "$(component_title "$component")"
    done
fi
failure=0 jdk_failed=false
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
for component in jdk gradle nvm iterm2 oh-my-zsh idea; do
    has_component "$component" || continue
    title="$(component_title "$component")"
    if [ "$component" = gradle ] && "$jdk_failed"; then
        printf '未执行 %s：JDK 依赖失败。\n' "$title"
        record_component "$component" skipped "$failure" - 'JDK 依赖失败，未执行'
        continue
    fi
    current_component="$component"
    export TEAM_TUI_COMPONENT="$component"
    [ "${TEAM_TUI_EVENTS:-0}" != 1 ] || printf '@@TEAM_TUI\tcomponent\t%s\trunning\t%s\n' "$component" "$title"
    printf '\n正在安装并配置：%s\n' "$title"
    component_run "$component" false 2>&1 | tee "$run_dir/$component.log"
    pipe_codes=("${PIPESTATUS[@]}")
    status="${pipe_codes[0]}"
    [ "${pipe_codes[1]}" -eq 0 ] || status="${pipe_codes[1]}"
    case "$status" in 129|130|143) record_component "$component" cancelled "$status" "$component.log"; current_component=''; exit "$status" ;; esac
    state=succeeded
    if [ "$status" -ne 0 ]; then
        state=failed; [ "$failure" -ne 0 ] || failure="$status"
        [ "$component" != jdk ] || jdk_failed=true
    fi
    record_component "$component" "$state" "$status" "$component.log"
    current_component=''
done
[ "$failure" -ne 0 ] || printf '\n所选组件已安装并验证；未执行项目构建。\n'
exit "$failure"
