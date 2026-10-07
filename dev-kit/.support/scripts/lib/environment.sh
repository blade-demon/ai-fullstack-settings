#!/bin/bash
# 只读探测库。调用方先加载 common.sh；本文件不加载环境或执行 Gradle。

probe_managed_configuration() {
    local value values=() version='' expected="${GRADLE_VERSION:-4.5.1}"
    PROBE_JDK_CONFIG=missing; PROBE_GRADLE_CONFIG=missing; PROBE_PROFILE_CONFIG=missing
    PROBE_CONFIG_JAVA_HOME=''; PROBE_CONFIG_JAVA_8_HOME=''; PROBE_CONFIG_JRE_HOME=''
    PROBE_CONFIG_GRADLE_HOME=''; PROBE_CONFIG_GRADLE_ALIAS=''; PROBE_CONFIG_GRADLE_USER_HOME=''
    PROBE_CONFIG_PATH=''; PROBE_CONFIG_JAVA_COMMAND=''; PROBE_CONFIG_GRADLE_COMMAND=''
    if [ -f "${ENV_FILE:-}" ]; then
        while IFS= read -r -d '' value; do values+=("$value"); done < <(
            /usr/bin/env -i HOME="$HOME" PATH='/usr/bin:/bin:/usr/sbin:/sbin' /bin/bash --noprofile --norc -c '
                source "$1" >/dev/null 2>&1 || exit 1
                gradle_alias="$2"
                printf "%s\0" "${JAVA_HOME:-}" "${JAVA_8_HOME:-}" "${JRE_HOME:-}" \
                    "${GRADLE_HOME:-}" "${!gradle_alias-}" "${GRADLE_USER_HOME:-}" "${PATH:-}" \
                    "$(command -v java 2>/dev/null || true)" "$(command -v gradle 2>/dev/null || true)"
            ' probe "$ENV_FILE" "$(gradle_alias_name)"
        )
        if [ "${#values[@]}" -eq 9 ]; then
            PROBE_CONFIG_JAVA_HOME="${values[0]}"; PROBE_CONFIG_JAVA_8_HOME="${values[1]}"; PROBE_CONFIG_JRE_HOME="${values[2]}"
            PROBE_CONFIG_GRADLE_HOME="${values[3]}"; PROBE_CONFIG_GRADLE_ALIAS="${values[4]}"; PROBE_CONFIG_GRADLE_USER_HOME="${values[5]}"
            PROBE_CONFIG_PATH="${values[6]}"; PROBE_CONFIG_JAVA_COMMAND="${values[7]}"; PROBE_CONFIG_GRADLE_COMMAND="${values[8]}"
            if [ -n "${PROBE_JDK_HOME:-}" ] && [ "$PROBE_CONFIG_JAVA_HOME" -ef "$PROBE_JDK_HOME" ] &&
                [ "$PROBE_CONFIG_JAVA_8_HOME" -ef "$PROBE_CONFIG_JAVA_HOME" ] && [ -d "$PROBE_CONFIG_JRE_HOME" ] &&
                [ "$PROBE_CONFIG_JRE_HOME" -ef "$PROBE_CONFIG_JAVA_HOME/jre" ] &&
                [ "$PROBE_CONFIG_JAVA_COMMAND" -ef "$PROBE_CONFIG_JAVA_HOME/bin/java" ]; then PROBE_JDK_CONFIG=ready; fi
            if [ -n "$PROBE_CONFIG_GRADLE_HOME" ]; then
                version="$(_probe_distribution_version "$PROBE_CONFIG_GRADLE_HOME")" || version=''
                if [ "$version" = "$expected" ] && [ "$PROBE_CONFIG_GRADLE_COMMAND" -ef "$PROBE_CONFIG_GRADLE_HOME/bin/gradle" ]; then
                    case "$PROBE_CONFIG_GRADLE_USER_HOME" in
                        /*) if [ "$PROBE_CONFIG_GRADLE_ALIAS" -ef "$PROBE_CONFIG_GRADLE_HOME" ]; then PROBE_GRADLE_CONFIG=ready; fi ;;
                    esac
                fi
            fi
        fi
    fi
    if command -v managed_env_profile_ready >/dev/null 2>&1 && managed_env_profile_ready; then PROBE_PROFILE_CONFIG=ready; fi
    return 0
}

verify_profile_configuration() {
    local scope="${1:-all}" value values=()
    while IFS= read -r -d '' value; do values+=("$value"); done < <(_managed_env_profile_values 2>/dev/null)
    [ "${#values[@]}" -eq 9 ] || return 1
    [ "${values[0]}" -ef "$PROBE_CONFIG_JAVA_HOME" ] &&
        [ "${values[1]}" -ef "$PROBE_CONFIG_JAVA_8_HOME" ] &&
        [ "${values[2]}" -ef "$PROBE_CONFIG_JRE_HOME" ] &&
        [ "${values[7]}" -ef "$PROBE_CONFIG_JAVA_HOME/bin/java" ] || return 1
    if [ "$scope" != jdk ]; then
        [ "${values[3]}" -ef "$PROBE_CONFIG_GRADLE_HOME" ] &&
            [ "${values[5]}" = "$PROBE_CONFIG_GRADLE_USER_HOME" ] &&
            [ "${values[8]}" -ef "$PROBE_CONFIG_GRADLE_HOME/bin/gradle" ] || return 1
        [ "${values[4]}" -ef "$PROBE_CONFIG_GRADLE_HOME" ] || return 1
    fi
    return 0
}

probe_idea() {
    local app="${IDEA_APP:-$HOME/Applications/IntelliJ IDEA CE.app}" plist identifier version build
    PROBE_IDEA_STATE=missing; PROBE_IDEA_PATH="$app"; PROBE_IDEA_VERSION=''; PROBE_IDEA_BUILD=''
    [ -d "$app" ] && [ ! -L "$app" ] || return 0
    PROBE_IDEA_STATE=invalid
    plist="$app/Contents/Info.plist"
    [ -f "$plist" ] && [ ! -L "$plist" ] || return 0
    identifier="$(plutil -extract CFBundleIdentifier raw -o - "$plist" 2>/dev/null)" || return 0
    version="$(plutil -extract CFBundleShortVersionString raw -o - "$plist" 2>/dev/null)" || return 0
    build="$(plutil -extract CFBundleVersion raw -o - "$plist" 2>/dev/null)" || return 0
    PROBE_IDEA_VERSION="$version"; PROBE_IDEA_BUILD="$build"
    [ "$identifier" = com.jetbrains.intellij.ce ] && [ "$version" = "${IDEA_VERSION:-2024.3.7.1}" ] || return 0
    [ "$build" = IC-243.28141.41 ] && [ -s "$app/Contents/MacOS/idea" ] && [ -x "$app/Contents/MacOS/idea" ] || return 0
    PROBE_IDEA_STATE=installed
    return 0
}

_probe_real_path() {
    local path="$1" link count=0 parent
    case "$path" in /*) ;; *) path="$(pwd -P)/$path" ;; esac
    while [ -L "$path" ]; do
        count=$((count + 1))
        [ "$count" -le 40 ] || return 1
        link="$(readlink "$path" 2>/dev/null)" || return 1
        case "$link" in /*) path="$link" ;; *) path="$(dirname -- "$path")/$link" ;; esac
    done
    [ -e "$path" ] || return 1
    if [ -d "$path" ]; then
        (CDPATH= cd -- "$path" && pwd -P) 2>/dev/null
    else
        parent="$(CDPATH= cd -- "$(dirname -- "$path")" && pwd -P)" || return 1
        printf '%s/%s\n' "$parent" "${path##*/}"
    fi
}

_probe_try_jdk8() {
    local candidate source="$2" version java_command javac_command
    [ -n "$1" ] || return 1
    candidate="$(_probe_real_path "$1")" || return 1
    # 系统 java 启动占位程序可能弹出安装窗口，不能用于只读探测。
    [ -x "$candidate/bin/java" ] && [ -x "$candidate/bin/javac" ] || return 1
    java_command="$(_probe_real_path "$candidate/bin/java")" || return 1
    javac_command="$(_probe_real_path "$candidate/bin/javac")" || return 1
    case "$java_command" in /usr/bin/java|/System/Library/Frameworks/JavaVM.framework/*) return 1 ;; esac
    case "$javac_command" in /usr/bin/javac|/System/Library/Frameworks/JavaVM.framework/*) return 1 ;; esac
    is_jdk8 "$candidate" || return 1
    version="$("$candidate/bin/java" -version 2>&1 | awk -F '"' '/version[ \t]+"/ {print $2; exit}')" || version=''
    PROBE_JDK_HOME="$candidate"
    PROBE_JDK_SOURCE="$source"
    PROBE_JDK_VERSION="$version"
    return 0
}

probe_jdk8() {
    local candidate='' command_path=''
    PROBE_JDK_HOME=''
    PROBE_JDK_SOURCE=''
    PROBE_JDK_VERSION=''
    if [ -n "${ENV_FILE:-}" ] && [ -f "$ENV_FILE" ]; then
        # 只加载此前生成的可信环境文件；其 JAVA_HOME/PATH 不进入调用者环境。
        candidate="$(
            unset JAVA_HOME
            source "$ENV_FILE" >/dev/null 2>&1 || exit 1
            printf '%s' "${JAVA_HOME:-}"
        )" || candidate=''
        if _probe_try_jdk8 "$candidate" env_file; then return 0; fi
    fi
    if _probe_try_jdk8 "${JAVA_HOME:-}" environment; then return 0; fi
    if [ -n "${JDK_INSTALL_DIR:-}" ]; then
        candidate="$(find_java_home "$JDK_INSTALL_DIR" 2>/dev/null)" || candidate=''
        if _probe_try_jdk8 "$candidate" managed; then return 0; fi
    fi
    if [ "${JDK_AUTO_DETECT:-true}" = true ]; then
        if [ -x /usr/libexec/java_home ]; then
            candidate="$(/usr/libexec/java_home -v 1.8 2>/dev/null)" || candidate=''
            if _probe_try_jdk8 "$candidate" registered; then return 0; fi
        fi
        command_path="$(type -P java 2>/dev/null)" || command_path=''
        if [ -n "$command_path" ]; then
            command_path="$(_probe_real_path "$command_path")" || command_path=''
            case "$command_path" in
                */bin/java)
                    if _probe_try_jdk8 "${command_path%/bin/java}" path; then return 0; fi ;;
            esac
        fi
    fi
    return 0
}

_probe_gradle_note() {
    PROBE_GRADLE_NOTE="${PROBE_GRADLE_NOTE:+${PROBE_GRADLE_NOTE}; }$1"
}

_probe_distribution_version() {
    local home="$1" jar version='' count=0
    [ -f "$home/bin/gradle" ] && [ -s "$home/bin/gradle" ] && [ -x "$home/bin/gradle" ] || return 1
    for jar in "$home"/lib/gradle-launcher-*.jar; do
        [ -f "$jar" ] || continue
        [ -s "$jar" ] || return 1
        count=$((count + 1))
        version="${jar##*/gradle-launcher-}"
        version="${version%.jar}"
    done
    [ "$count" -eq 1 ] && [ -n "$version" ] || return 1
    printf '%s' "$version"
}

_probe_gradle_global() {
    local command_path='' resolved='' home='' version=''
    command_path="$(type -P gradle 2>/dev/null)" || command_path=''
    if [ -n "$command_path" ]; then
        case "$command_path" in /*) ;; *) command_path="$(pwd -P)/$command_path" ;; esac
        PROBE_GRADLE_GLOBAL_COMMAND="$command_path"
        resolved="$(_probe_real_path "$command_path")" || resolved=''
        case "$resolved" in
            */bin/gradle)
                version="$(_probe_distribution_version "${resolved%/bin/gradle}")" || version=''
                PROBE_GRADLE_GLOBAL_VERSION="$version" ;;
        esac
    elif [ -n "${GRADLE_HOME:-}" ]; then
        home="$(_probe_real_path "$GRADLE_HOME")" || home=''
        if [ -n "$home" ]; then
            version="$(_probe_distribution_version "$home")" || version=''
            if [ -n "$version" ]; then
                PROBE_GRADLE_GLOBAL_COMMAND="$home/bin/gradle"
                PROBE_GRADLE_GLOBAL_VERSION="$version"
            fi
        fi
    fi
    if [ -n "$PROBE_GRADLE_GLOBAL_COMMAND" ] && [ -z "$PROBE_GRADLE_GLOBAL_VERSION" ]; then
        _probe_gradle_note 'PATH 中存在 Gradle 命令，但无法从分发结构确定版本；未运行该命令'
        if [ -n "${GRADLE_HOME:-}" ]; then
            version="$(_probe_distribution_version "$GRADLE_HOME")" || version=''
            if [ -n "$version" ]; then _probe_gradle_note "GRADLE_HOME 另有 ${version} 分发，未认定它就是 PATH 命令"; fi
        fi
    fi
    return 0
}

# Wrapper 完成目录必须只有一个顶层目录，且该目录包含目标版本的启动文件。
_probe_cache_distribution() {
    local root="$1" version="$2" child found='' count=0 observed
    [ -d "$root" ] || return 1
    for child in "$root"/* "$root"/.[!.]* "$root"/..?*; do
        [ -d "$child" ] || continue
        count=$((count + 1))
        found="$child"
    done
    [ "$count" -eq 1 ] || return 1
    observed="$(_probe_distribution_version "$found")" || return 1
    [ "$observed" = "$version" ] || return 1
    _probe_real_path "$found"
}

_probe_gradle_inventory() {
    local user_home="$1" version="$2" hash_dir stem app
    PROBE_GRADLE_CACHED_PATHS=''
    for hash_dir in "$user_home"/wrapper/dists/*/*; do
        [ -d "$hash_dir" ] || continue
        stem="${hash_dir%/*}"; stem="${stem##*/}"
        [ -f "$hash_dir/$stem.zip.ok" ] || continue
        app="$(_probe_cache_distribution "$hash_dir" "$version")" || continue
        [ "$app" != "$PROBE_GRADLE_PATH" ] || continue
        PROBE_GRADLE_CACHED_PATHS="${PROBE_GRADLE_CACHED_PATHS:+${PROBE_GRADLE_CACHED_PATHS}
}$app"
    done
    return 0
}

# 支持常见 Java properties 分隔、转义及 CRLF；续行、Unicode/控制转义保守判未知。
_probe_wrapper_properties() {
    LC_ALL=C awk '
        function decode(s,    i,c,n,out) {
            out=""
            for (i=1; i<=length(s); i++) {
                c=substr(s,i,1)
                if (c=="\\") {
                    if (++i>length(s)) {bad=1; return ""}
                    n=substr(s,i,1)
                    if (n ~ /^[utnrf]$/) {bad=1; return ""}
                    c=n
                }
                if (c ~ /[[:cntrl:]]/) {bad=1; return ""}
                out=out c
            }
            return out
        }
        {
            line=$0; sub(/\r$/, "", line); sub(/^[ \t\f]+/, "", line)
            if (line=="" || line ~ /^[#!]/) next
            tail=line; slashes=0
            while (substr(tail,length(tail),1)=="\\") {slashes++; tail=substr(tail,1,length(tail)-1)}
            if (slashes%2) {bad=1; next}
            escaped=0
            for (i=1; i<=length(line); i++) {
                c=substr(line,i,1)
                if (escaped) {escaped=0; continue}
                if (c=="\\") {escaped=1; continue}
                if (c ~ /[ \t\f=:]/) break
            }
            key=decode(substr(line,1,i-1))
            if (key !~ /^(distributionUrl|distributionBase|distributionPath|zipStoreBase|zipStorePath)$/) next
            value=substr(line,i); sub(/^[ \t\f]+/, "", value)
            sub(/^[=:]/, "", value); sub(/^[ \t\f]+/, "", value)
            values[key]=decode(value); present[key]=1
        }
        END {
            if (bad) exit 1
            split("distributionUrl distributionBase distributionPath zipStoreBase zipStorePath", keys, " ")
            for (i=1; i<=5; i++) if (present[keys[i]]) printf "%s\t%s\n", keys[i], values[keys[i]]
        }
    ' "$1"
}

# 逐个十六进制数字长除以 36，中间值不超过 575，不用浮点表示 128 位 MD5。
_probe_wrapper_url_hash() {
    local url="$1" digest=''
    if command -v md5 >/dev/null 2>&1; then
        digest="$(printf '%s' "$url" | md5 -q 2>/dev/null)" || return 1
    elif command -v openssl >/dev/null 2>&1; then
        digest="$(printf '%s' "$url" | openssl dgst -md5 2>/dev/null)" || return 1
        digest="${digest##* }"
    else
        return 1
    fi
    [ "${#digest}" -eq 32 ] || return 1
    case "$digest" in *[!a-fA-F0-9]*) return 1 ;; esac
    printf '%s\n' "$digest" | LC_ALL=C awk '
        { number=tolower($0); hex="0123456789abcdef"; alphabet="0123456789abcdefghijklmnopqrstuvwxyz"; answer=""
          while (number!="" && number!="0") {
              quotient=""; carry=0
              for (i=1; i<=length(number); i++) {
                  value=carry*16+index(hex,substr(number,i,1))-1
                  digit=int(value/36); carry=value%36
                  if (quotient!="" || digit!=0) quotient=quotient substr(hex,digit+1,1)
              }
              answer=substr(alphabet,carry+1,1) answer; number=quotient
          }
          print (answer=="" ? "0" : answer)
        }
    '
}

_probe_ascii_uri() {
    local LC_ALL=C pattern='^[ -~]+$'
    [[ "$1" =~ $pattern ]]
}

probe_gradle() {
    local project="${1:-}" override="${2:-}" version="${GRADLE_VERSION:-4.5.1}"
    local user_home="${GRADLE_USER_HOME:-${HOME:-}/.gradle}" file props parsed key value
    local url='' distribution_base=GRADLE_USER_HOME distribution_path=wrapper/dists
    local zip_base=GRADLE_USER_HOME zip_path=wrapper/dists origin path name stem hash dist_root zip_root app options
    PROBE_GRADLE_STATE=no_project
    PROBE_GRADLE_PATH=''
    PROBE_GRADLE_URL=''
    PROBE_GRADLE_NOTE=''
    PROBE_GRADLE_GLOBAL_COMMAND=''
    PROBE_GRADLE_GLOBAL_VERSION=''
    PROBE_GRADLE_CACHED_PATHS=''
    PROBE_WRAPPER_MISSING=''
    _probe_gradle_global
    options="${JAVA_OPTS:-} ${GRADLE_OPTS:-} ${JAVA_TOOL_OPTIONS:-} ${_JAVA_OPTIONS:-} ${JDK_JAVA_OPTIONS:-}"
    if [ -n "$project" ] && [ -d "$project" ]; then
        project="$(CDPATH= cd -- "$project" && pwd -P)" || project=''
    fi
    case "$user_home" in /*) ;; *) user_home="${project:-$(pwd -P)}/$user_home" ;; esac
    _probe_gradle_inventory "$user_home" "$version"
    if [ -z "$project" ]; then
        case "$options" in
            *-Dgradle.user.home*|*-Duser.home*)
                _probe_gradle_note '存在 JVM 用户目录覆盖；库存仅来自默认 GRADLE_USER_HOME 目录，不代表命令实际使用的缓存' ;;
        esac
        return 0
    fi

    for file in gradlew gradle/wrapper/gradle-wrapper.jar gradle/wrapper/gradle-wrapper.properties; do
        if [ ! -s "$project/$file" ]; then
            PROBE_WRAPPER_MISSING="${PROBE_WRAPPER_MISSING:+${PROBE_WRAPPER_MISSING}
}$file"
        fi
    done
    if [ -n "$PROBE_WRAPPER_MISSING" ]; then
        PROBE_GRADLE_STATE=wrapper_missing
        _probe_gradle_note '项目 Wrapper 文件不完整；未运行或修改项目'
        return 0
    fi
    PROBE_GRADLE_STATE=unknown
    case "$options" in
        *-Dgradle.user.home*|*-Duser.home*)
            _probe_gradle_note 'JVM 选项覆盖 Gradle 用户目录或 user.home，无法静态确定实际缓存位置'
            return 0 ;;
    esac
    if LC_ALL=C awk '/-D(gradle[.]user[.]home|user[.]home)(=|[[:space:]])/ {found=1} END {exit !found}' "$project/gradlew" 2>/dev/null; then
        _probe_gradle_note 'Wrapper 脚本包含用户目录覆盖，无法静态确定实际缓存位置'
        return 0
    fi
    props="$project/gradle/wrapper/gradle-wrapper.properties"
    parsed="$(_probe_wrapper_properties "$props")" || {
        _probe_gradle_note 'Wrapper properties 含续行或不支持的转义，无法静态确定缓存位置'
        return 0
    }
    while IFS=$'\t' read -r key value; do
        case "$key" in
            distributionUrl) url="$value" ;;
            distributionBase) distribution_base="$value" ;;
            distributionPath) distribution_path="$value" ;;
            zipStoreBase) zip_base="$value" ;;
            zipStorePath) zip_path="$value" ;;
        esac
    done <<< "$parsed"
    [ -z "$override" ] || url="$override"
    PROBE_GRADLE_URL="$url"
    if ! _probe_ascii_uri "$url"; then
        _probe_gradle_note '下载 URI 含非 ASCII 字符或为空，JVM 字符编码未知，无法静态确定缓存键'
        return 0
    fi
    case "$distribution_base:$zip_base" in
        GRADLE_USER_HOME:GRADLE_USER_HOME|PROJECT:GRADLE_USER_HOME|GRADLE_USER_HOME:PROJECT|PROJECT:PROJECT) ;;
        *) _probe_gradle_note '不支持的 Wrapper 缓存基准目录（仅识别 PROJECT 与 GRADLE_USER_HOME）'; return 0 ;;
    esac
    case "$distribution_path:$zip_path" in
        /*|*:/*) _probe_gradle_note 'Wrapper 使用绝对缓存子路径，无法静态确认其解析方式'; return 0 ;;
    esac
    case "$url" in
        http://*|https://*)
            origin="${url#*://}"; origin="${origin%%/*}"
            case "$origin" in ''|*@*) _probe_gradle_note '下载 URI 含用户信息或缺少主机，无法安全确定缓存键'; return 0 ;; esac ;;
        file:/*) ;;
        *) _probe_gradle_note '缺少绝对下载 URI，无法静态确定 Wrapper 缓存键'; return 0 ;;
    esac
    case "$url" in
        *[[:space:]]*|*'\'*|*'{'*|*'}'*|*'<'*|*'>'*|*'"'*|*'`'*|*'|'*|*'^'*)
            _probe_gradle_note '下载 URI 格式复杂或包含不支持字符，无法静态确定缓存键'; return 0 ;;
    esac
    path="${url%%\#*}"; path="${path%%\?*}"
    name="${path##*/}"; stem="${name%.*}"
    case "$name" in ''|*%*) _probe_gradle_note '下载 URI 的文件名为空或需要解码，无法静态确定缓存路径'; return 0 ;; esac
    if [ "$stem" = "$name" ] || [ -z "$stem" ]; then
        _probe_gradle_note '下载 URI 没有可识别的分发文件名'; return 0
    fi
    hash="$(_probe_wrapper_url_hash "$url")" || {
        _probe_gradle_note '缺少可用 MD5 工具，无法计算 Wrapper 缓存目录'; return 0
    }
    if [ "$distribution_base" = PROJECT ]; then dist_root="$project"; else dist_root="$user_home"; fi
    if [ "$zip_base" = PROJECT ]; then zip_root="$project"; else zip_root="$user_home"; fi
    dist_root="$dist_root/$distribution_path/$stem/$hash"
    zip_root="$zip_root/$zip_path/$stem/$hash"
    PROBE_GRADLE_STATE=project_missing
    if [ -f "$zip_root/$name.ok" ]; then
        app="$(_probe_cache_distribution "$dist_root" "$version")" || app=''
        if [ -n "$app" ]; then
            PROBE_GRADLE_STATE=project_cached
            PROBE_GRADLE_PATH="$app"
            _probe_gradle_note "项目对应的 Gradle ${version} 缓存完整；未运行验证"
            _probe_gradle_inventory "$user_home" "$version"
            return 0
        fi
    fi
    _probe_gradle_note "当前下载地址对应的 Gradle ${version} 缓存缺失或不完整；未下载、未运行"
    return 0
}
