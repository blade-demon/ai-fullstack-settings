#!/bin/bash
# 插件 ZIP/JAR 的静态核验；兼容系统 Bash 3.2，不执行插件代码。
PLUGIN_RECEIPT='.team-java-env-plugin-receipt.tsv'

plugin_error() { printf '插件校验失败：%s\n' "$*" >&2; return 1; }
plugin_hash() {
    local digest
    digest="$(shasum -a 256 < "$1")" || return 1
    printf '%s' "${digest%% *}"
}
plugin_safe_directory() {
    local path="$1"
    while [ "$path" != / ] && [ "${path%/}" != "$path" ]; do path="${path%/}"; done
    while :; do
        [ ! -L "$path" ] || { plugin_error "目录不能经过符号链接：$path"; return 1; }
        if [ -e "$path" ] && [ ! -d "$path" ]; then plugin_error "目录位置已有其他文件：$path"; return 1; fi
        [ "$path" != / ] && [ "$path" != . ] || break
        path="$(dirname -- "$path")"
    done
}
plugin_safe_relative() {
    case "$1" in ''|/*|.|..|./*|../*|*/../*|*/..|*/./*|*/.|*//*|*\\*|*[[:cntrl:]]*) return 1 ;; esac
    printf '%s\n' "$1" | LC_ALL=C awk '/^[A-Za-z0-9_. +()@\/-]+$/ {ok=1} END {exit !ok}'
}
plugin_build_compatible() {
    LC_ALL=C awk -v build="$1" -v lower="$2" -v upper="$3" '
      function compare(a,b,upper, x,y,n,m,i) {
        n=split(a,x,"."); m=split(b,y,".");
        for(i=1;i<=n || i<=m;i++) {
          if (upper && y[i]=="*") return 0;
          if (x[i]+0 < y[i]+0) return -1;
          if (x[i]+0 > y[i]+0) return 1;
        }
        return 0;
      }
      BEGIN {
        if (build !~ /^[0-9]+(\.[0-9]+)*$/ || lower !~ /^[0-9]+(\.[0-9]+)*$/) exit 1;
        if (upper!="" && upper!~/^[0-9]+(\.[0-9]+)*(\.\*)?$/) exit 1;
        if (compare(build,lower,0)<0 || (upper!="" && compare(build,upper,1)>0)) exit 1;
      }'
}

plugin_archive_root() {
    local zip="$1" scratch="$2" entry root='' first
    unzip -tqq "$zip" >/dev/null 2>&1 || { plugin_error "ZIP 无法完整读取：$zip"; return 1; }
    unzip -Z -1 "$zip" > "$scratch/entries" || return 1
    unzip -Z -l "$zip" > "$scratch/modes" || return 1
    # ZIP 的 Unix 符号链接/特殊文件必须在解压前拒绝。
    if LC_ALL=C awk '$1 ~ /^[lbcps][rwxstST-]/ {bad=1} END {exit !bad}' "$scratch/modes"; then
        plugin_error "ZIP 包含符号链接或特殊文件：$zip"; return 1
    fi
    LC_ALL=C awk 'seen[$0]++ {bad=1} END {exit bad}' "$scratch/entries" || { plugin_error 'ZIP 包含重复路径'; return 1; }
    while IFS= read -r entry || [ -n "$entry" ]; do
        plugin_safe_relative "${entry%/}" || { plugin_error "ZIP 路径不安全：$entry"; return 1; }
        case "$entry" in */*) ;; *) plugin_error 'ZIP 必须包含一个顶层插件目录'; return 1 ;; esac
        first="${entry%%/*}"
        case "$first" in [A-Za-z0-9]*) ;; *) plugin_error '插件目录名称无效'; return 1 ;; esac
        if [ -z "$root" ]; then root="$first"; fi
        [ "$first" = "$root" ] || { plugin_error 'ZIP 包含多个顶层目录'; return 1; }
    done < "$scratch/entries"
    [ -n "$root" ] || return 1
    printf '%s' "$root"
}

plugin_metadata() {
    local directory="$1" scratch="$2" jar found=0 xml="$2/plugin.xml" value count index dependency
    PLUGIN_XML_ID=''; PLUGIN_VERSION=''; PLUGIN_SINCE=''; PLUGIN_UNTIL=''
    [ -d "$directory" ] && [ ! -L "$directory" ] || return 1
    [ -z "$(find "$directory" -type l -print -quit)" ] || return 1
    find "$directory" -type f -name '*.jar' -print > "$scratch/jars" || return 1
    while IFS= read -r jar; do
        [ -s "$jar" ] && [ -r "$jar" ] || return 1
        if unzip -p "$jar" META-INF/plugin.xml > "$xml" 2>/dev/null; then
            found=$((found + 1))
            [ "$found" -eq 1 ] || { plugin_error "插件描述文件不唯一：$directory"; return 1; }
            if LC_ALL=C grep -Eq '<!DOCTYPE|<!ENTITY' "$xml"; then return 1; fi
            xmllint --nonet --noout "$xml" 2>/dev/null || return 1
            PLUGIN_XML_ID="$(xmllint --nonet --xpath 'normalize-space(/idea-plugin/id)' "$xml" 2>/dev/null)" || return 1
            if [ -z "$PLUGIN_XML_ID" ]; then
                PLUGIN_XML_ID="$(xmllint --nonet --xpath 'normalize-space(/idea-plugin/name)' "$xml" 2>/dev/null)" || return 1
            fi
            PLUGIN_VERSION="$(xmllint --nonet --xpath 'normalize-space(/idea-plugin/version)' "$xml" 2>/dev/null)" || return 1
            PLUGIN_SINCE="$(xmllint --nonet --xpath 'string(/idea-plugin/idea-version/@since-build)' "$xml" 2>/dev/null)" || return 1
            PLUGIN_UNTIL="$(xmllint --nonet --xpath 'string(/idea-plugin/idea-version/@until-build)' "$xml" 2>/dev/null)" || return 1
            for value in "$PLUGIN_XML_ID" "$PLUGIN_VERSION" "$PLUGIN_SINCE"; do
                [ -n "$value" ] || return 1
                case "$value" in *[[:cntrl:]]*) return 1 ;; esac
            done
            count="$(xmllint --nonet --xpath 'count(/idea-plugin/depends[not(@optional="true")])' "$xml" 2>/dev/null)" || return 1
            index=1
            while [ "$index" -le "$count" ]; do
                dependency="$(xmllint --nonet --xpath "normalize-space((/idea-plugin/depends[not(@optional='true')])[$index])" "$xml" 2>/dev/null)" || return 1
                case "$dependency" in
                    com.intellij.modules.platform|com.intellij.modules.lang|com.intellij.modules.java|com.intellij.java) ;;
                    *) plugin_error "需要额外必需依赖：$dependency"; return 1 ;;
                esac
                index=$((index + 1))
            done
            count="$(xmllint --nonet --xpath 'count(/idea-plugin/dependencies/*)' "$xml" 2>/dev/null)" || return 1
            [ "$count" = 0 ] || { plugin_error '存在尚未核验的新式插件依赖'; return 1; }
        fi
    done < "$scratch/jars"
    [ "$found" -eq 1 ]
}

plugin_receipt_identity() {
    local directory="$1" key="$2" receipt="$1/$PLUGIN_RECEIPT"
    [ -f "$receipt" ] && [ ! -L "$receipt" ] || return 1
    LC_ALL=C awk -F '\t' -v key="$key" '
      NR==1 && $0!="# team-java-env-plugin-v1" {bad=1}
      $1==key {value=$2; count++; if(NF!=2) bad=1}
      END {if(bad || count!=1 || value=="") exit 1; print value}' "$receipt"
}

# 根据实际文件重建收据，以整文件比较验证 metadata、归档来源及所有安装文件。
plugin_make_receipt() {
    local directory="$1" rid="$2" expected_version="$3" archive_sha="$4" build="$5" output="$6" scratch="$7"
    local file relative digest jar_count=0
    plugin_metadata "$directory" "$scratch" || { plugin_error "无法读取插件元数据：$directory"; return 1; }
    [ "$PLUGIN_VERSION" = "$expected_version" ] || { plugin_error "版本不匹配：$rid ($PLUGIN_VERSION / $expected_version)"; return 1; }
    plugin_build_compatible "$build" "$PLUGIN_SINCE" "$PLUGIN_UNTIL" || { plugin_error "不兼容当前 IDEA build：$rid ($PLUGIN_SINCE — $PLUGIN_UNTIL)"; return 1; }
    {
        printf '# team-java-env-plugin-v1\nresource_id\t%s\nplugin_id\t%s\nversion\t%s\narchive_sha256\t%s\nide_build\t%s\n' \
            "$rid" "$PLUGIN_XML_ID" "$expected_version" "$archive_sha" "$build"
    } > "$output" || return 1
    find "$directory" -type f ! -path "$directory/$PLUGIN_RECEIPT" -print | LC_ALL=C sort > "$scratch/files" || return 1
    while IFS= read -r file; do
        relative="${file#"$directory/"}"
        plugin_safe_relative "$relative" || return 1
        [ -r "$file" ] || return 1
        case "$file" in *.jar)
            [ -s "$file" ] || return 1
            unzip -tqq "$file" >/dev/null 2>&1 || { plugin_error "JAR 损坏：$file"; return 1; }
            jar_count=$((jar_count + 1)) ;;
        esac
        digest="$(plugin_hash "$file")" || return 1
        printf 'file\t%s\t%s\n' "$digest" "$relative" >> "$output" || return 1
    done < "$scratch/files"
    [ "$jar_count" -gt 0 ]
}

plugin_verify_installed() {
    local directory="$1" rid="$2" version="$3" hash="$4" build="$5" scratch="$6"
    [ -f "$directory/$PLUGIN_RECEIPT" ] && [ ! -L "$directory/$PLUGIN_RECEIPT" ] || return 1
    plugin_make_receipt "$directory" "$rid" "$version" "$hash" "$build" "$scratch/expected-receipt" "$scratch" || return 1
    cmp -s "$scratch/expected-receipt" "$directory/$PLUGIN_RECEIPT"
}
