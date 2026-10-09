#!/bin/bash
# 维护者与成员共用的清单下载器：只保存资源，不运行安装包。
set -euo pipefail
umask 022

ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [ -f "$ROOT/scripts/lib/download-progress.sh" ]; then
  source "$ROOT/scripts/lib/download-progress.sh"
elif [ -f "$ROOT/dev-kit/.support/scripts/lib/download-progress.sh" ]; then
  source "$ROOT/dev-kit/.support/scripts/lib/download-progress.sh"
else
  # 维护者可以单独复制这个清单下载器；TUI 成员包必须带进度模块。
  team_download() {
    local destination="$1" url="$2"; shift 2
    [ "${TEAM_TUI_EVENTS:-0}" != 1 ] || { printf '进度模块缺失，请重新获取完整工具包。\n' >&2; return 1; }
    curl --disable --fail --location --silent --show-error --proto '=http,https' --proto-redir '=http,https' --output "$destination" "$@" -- "$url"
  }
fi
OUTPUT="$ROOT/resources"
CATALOG="$ROOT/resources/catalog.tsv"
GROUP=all
ARCH=all
SELECT_ID=""
MODE=download
PART=""
RECEIPT_PART=""

die() { printf '资源准备失败：%s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'HELP'
用法：bash tools/prepare-resources.sh [--output 目录] [--catalog 清单]
       [--group all|runtime|software|plugins] [--arch all|arm64|x64|any]
       [--id 资源ID] [--dry-run | --verify]

默认读取项目 resources/catalog.tsv，资源保存到项目 resources。
--dry-run 只显示清单，不写文件、不联网。
--verify 只校验已有资源，不下载、不补写校验文件。
--id 只选择一个资源；arm64/x64 架构选择也包含 any 通用资源。
已有资源校验失败时会保留原文件，请审核并移走后再重试。
清单没有上游 SHA-256 时，首次下载生成的 .sha256 仅记录本地完整性，
不代表经过上游哈希认证；没有该记录的既有资源需要先人工审核。
HELP
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --output|--catalog|--group|--arch|--id)
      [ "$#" -ge 2 ] && [ -n "$2" ] || die "$1 需要一个值。"
      case "$2" in --*) die "$1 缺少有效值。" ;; esac
      case "$1" in
        --output) OUTPUT="$2" ;;
        --catalog) CATALOG="$2" ;;
        --group) GROUP="$2" ;;
        --arch) ARCH="$2" ;;
        --id) SELECT_ID="$2" ;;
      esac
      shift 2 ;;
    --dry-run|--verify)
      [ "$MODE" = download ] || die '--dry-run 与 --verify 不能同时使用或重复指定。'
      case "$1" in --dry-run) MODE=plan ;; --verify) MODE=verify ;; esac
      shift ;;
    --help|-h) usage; exit 0 ;;
    *) die "未知参数：$1（使用 --help 查看用法）。" ;;
  esac
done
case "$GROUP" in all|runtime|software|plugins) ;; *) die "未知分组：$GROUP" ;; esac
case "$ARCH" in all|arm64|x64|any) ;; *) die "未知架构：$ARCH" ;; esac
case "$OUTPUT" in /*) ;; *) OUTPUT="$(pwd -P)/$OUTPUT" ;; esac
while [ "$OUTPUT" != / ] && [ "${OUTPUT%/}" != "$OUTPUT" ]; do OUTPUT="${OUTPUT%/}"; done
[ -f "$CATALOG" ] || die "找不到资源清单：$CATALOG"

# 检查每一级已存在目录；尚未创建的目录也不能经过符号链接。
check_directory() {
  local probe="$1"
  while :; do
    [ ! -L "$probe" ] || die "目录不能经过符号链接：$probe"
    if [ -e "$probe" ] && [ ! -d "$probe" ]; then
      die "目录位置已有其他文件：$probe"
    fi
    [ "$probe" != / ] && [ "$probe" != . ] || break
    probe="$(dirname -- "$probe")"
  done
}
check_target() {
  local target="$1"
  check_directory "$(dirname -- "$target")"
  [ ! -L "$target" ] || die "资源或校验文件不能是符号链接：$target"
  if [ -e "$target" ] && [ ! -f "$target" ]; then
    die "资源或校验文件位置不是普通文件：$target"
  fi
}
check_directory "$OUTPUT"

IDS=()
GROUPS_LIST=()
VERSIONS=()
ARCHES=()
PATHS=()
URLS=()
HASHES=()
COUNT=0
LINE_NO=0
TAB=$'\t'
HEADER="# id${TAB}group${TAB}version${TAB}arch${TAB}path${TAB}url${TAB}sha256"
HASH_PATTERN='^[[:xdigit:]]{64}$'
ID_PATTERN='^[A-Za-z0-9][A-Za-z0-9._-]*$'
URL_PATTERN='^https?://[^[:space:]]+$'

# 先把整个清单读完并验证，再开始任何目录创建、校验写入或网络请求。
while IFS= read -r line || [ -n "$line" ]; do
  LINE_NO=$((LINE_NO + 1))
  if [ "$LINE_NO" -eq 1 ]; then
    [ "$line" = "$HEADER" ] || die '清单首行必须为 # id、group、version、arch、path、url、sha256（制表符分隔）。'
    continue
  fi
  case "$line" in ''|'#'*) continue ;; esac
  fields=()
  rest="$line"
  field_index=0
  while [ "$field_index" -lt 6 ]; do
    case "$rest" in
      *"$TAB"*) fields[$field_index]="${rest%%"$TAB"*}"; rest="${rest#*"$TAB"}" ;;
      *) die "清单第 $LINE_NO 行必须恰好包含 7 列。" ;;
    esac
    field_index=$((field_index + 1))
  done
  case "$rest" in *"$TAB"*) die "清单第 $LINE_NO 行超过 7 列。" ;; esac
  fields[6]="$rest"
  for field in "${fields[@]}"; do
    [ -n "$field" ] || die "清单第 $LINE_NO 行含空字段（没有上游 SHA-256 时请填 -）。"
    case "$field" in *[[:cntrl:]]*) die "清单第 $LINE_NO 行包含控制字符。" ;; esac
  done
  id="${fields[0]}"; group="${fields[1]}"; version="${fields[2]}"
  arch="${fields[3]}"; relative="${fields[4]}"; url="${fields[5]}"; sha="${fields[6]}"
  [[ "$id" =~ $ID_PATTERN ]] || die "清单第 $LINE_NO 行的资源 ID 无效：$id"
  case "$group" in runtime|software|plugins) ;; *) die "清单第 $LINE_NO 行含未知分组：$group" ;; esac
  case "$relative" in
    /*|..|../*|*/..|*/../*|.|./*|*/.|*/./*|*/|*//*) die "清单第 $LINE_NO 行的路径不是安全相对路径：$relative" ;;
  esac
  [[ "$url" =~ $URL_PATTERN ]] || die "清单第 $LINE_NO 行的 URL 必须为 HTTP(S)：$url"
  if [ "$sha" != - ]; then
    [[ "$sha" =~ $HASH_PATTERN ]] || die "清单第 $LINE_NO 行的 SHA-256 必须是 64 位十六进制或 -。"
    sha="$(printf '%s' "$sha" | tr 'A-F' 'a-f')"
  fi
  previous=0
  while [ "$previous" -lt "$COUNT" ]; do
    [ "$id" != "${IDS[$previous]}" ] || die "清单有重复资源 ID：$id"
    # 资源与自动生成的 .sha256 不能重名，也不能占据另一资源的目录。
    for left in "$relative" "$relative.sha256"; do
      for right in "${PATHS[$previous]}" "${PATHS[$previous]}.sha256"; do
        case "$left/" in "$right/"*) die "清单资源路径冲突：$relative 与 ${PATHS[$previous]}" ;; esac
        case "$right/" in "$left/"*) die "清单资源路径冲突：$relative 与 ${PATHS[$previous]}" ;; esac
      done
    done
    previous=$((previous + 1))
  done
  check_target "$OUTPUT/$relative"
  check_target "$OUTPUT/$relative.sha256"
  IDS[$COUNT]="$id"; GROUPS_LIST[$COUNT]="$group"; VERSIONS[$COUNT]="$version"
  ARCHES[$COUNT]="$arch"; PATHS[$COUNT]="$relative"; URLS[$COUNT]="$url"; HASHES[$COUNT]="$sha"
  COUNT=$((COUNT + 1))
done < "$CATALOG"
[ "$LINE_NO" -gt 0 ] || die '资源清单为空。'
[ "$COUNT" -gt 0 ] || die '资源清单没有资源条目。'

SELECTED=()
SELECTED_COUNT=0
ID_FOUND=false
index=0
while [ "$index" -lt "$COUNT" ]; do
  selected=true
  if [ -n "$SELECT_ID" ]; then
    if [ "$SELECT_ID" = "${IDS[$index]}" ]; then ID_FOUND=true; else selected=false; fi
  fi
  if [ "$GROUP" != all ] && [ "$GROUP" != "${GROUPS_LIST[$index]}" ]; then selected=false; fi
  if [ "$ARCH" != all ]; then
    case "$ARCH:${ARCHES[$index]}" in
      any:any|arm64:any|arm64:arm64|arm64:macos-arm64|x64:any|x64:x64|x64:macos-x64) ;;
      *) selected=false ;;
    esac
  fi
  if [ "$selected" = true ]; then
    SELECTED[$SELECTED_COUNT]="$index"
    SELECTED_COUNT=$((SELECTED_COUNT + 1))
  fi
  index=$((index + 1))
done
[ -z "$SELECT_ID" ] || [ "$ID_FOUND" = true ] || die "未知资源 ID：$SELECT_ID"
[ "$SELECTED_COUNT" -gt 0 ] || die '没有符合分组、架构和资源 ID 条件的条目。'

if [ "$MODE" = plan ]; then
  for index in "${SELECTED[@]}"; do
    printf '计划：%s [%s / %s / %s]\n  %s\n  → %s/%s\n' \
      "${IDS[$index]}" "${GROUPS_LIST[$index]}" "${VERSIONS[$index]}" "${ARCHES[$index]}" \
      "${URLS[$index]}" "$OUTPUT" "${PATHS[$index]}"
  done
  printf '计划资源：%s；未写入文件或联网。\n' "$SELECTED_COUNT"
  exit 0
fi

if command -v shasum >/dev/null 2>&1; then
  HASH_TOOL=shasum
elif command -v sha256sum >/dev/null 2>&1; then
  HASH_TOOL=sha256sum
else
  die '缺少 SHA-256 工具：需要系统 shasum 或 sha256sum。'
fi
if [ "$MODE" = download ]; then
  command -v curl >/dev/null 2>&1 || die '缺少系统 curl。'
  command -v mktemp >/dev/null 2>&1 || die '缺少系统 mktemp。'
fi

cleanup() {
  [ -z "$PART" ] || rm -f -- "$PART"
  [ -z "$RECEIPT_PART" ] || rm -f -- "$RECEIPT_PART"
  return 0
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

hash_file() {
  local value
  if [ "$HASH_TOOL" = shasum ]; then
    value="$(shasum -a 256 < "$1")" || die "无法读取资源并计算 SHA-256：$1"
  else
    value="$(sha256sum < "$1")" || die "无法读取资源并计算 SHA-256：$1"
  fi
  printf '%s\n' "${value%% *}"
}
receipt_hash() {
  local target="$1" receipt="$1.sha256" first extra digest name
  [ -f "$receipt" ] || die "已有资源没有本地校验记录，请先人工审核；审核后移走该文件再重新下载：$target"
  {
    IFS= read -r first || [ -n "$first" ] || die "本地校验记录为空：$receipt"
    if IFS= read -r extra || [ -n "$extra" ]; then die "本地校验记录应只有一行：$receipt"; fi
  } < "$receipt"
  digest="${first%% *}"
  [[ "$digest" =~ $HASH_PATTERN ]] || die "本地校验记录格式无效：$receipt"
  name="${target##*/}"
  [ "$first" = "$digest  $name" ] || die "本地校验记录文件名不匹配：$receipt"
  printf '%s' "$digest" | tr 'A-F' 'a-f'
}
write_receipt() {
  local target="$1" digest="$2" expected current=""
  expected="$digest  ${target##*/}"
  check_target "$target.sha256"
  if [ -f "$target.sha256" ]; then current="$(cat -- "$target.sha256")"; fi
  [ "$current" != "$expected" ] || return 0
  RECEIPT_PART="$(mktemp "$target.sha256.part.XXXXXXXX")" || die "无法创建校验临时文件：$target"
  printf '%s\n' "$expected" > "$RECEIPT_PART" || die "无法写入校验记录：$target"
  chmod 644 "$RECEIPT_PART" || die "无法设置校验记录读取权限：$target"
  check_target "$target.sha256"
  mv -f -- "$RECEIPT_PART" "$target.sha256" || die "无法保存校验记录：$target"
  RECEIPT_PART=""
}

download_file() {
  local destination="$1" url="$2" attempt status
  for attempt in 1 2 3; do
    if TEAM_DOWNLOAD_ATTEMPT="$attempt" team_download "$destination" "$url" \
      --connect-timeout 30 --max-time 7200 --retry 2 --retry-delay 2; then
      return 0
    else
      status=$?
    fi
    # curl 默认重试不涵盖传输被截断；仅对连接/传输故障重试，不重试证书或404错误。
    case "$status" in
      6|7|18|28|52|55|56)
        [ "$attempt" -lt 3 ] || return "$status"
        printf '连接中断，正在重试下载（%s/3）…\n' "$((attempt + 1))"
        sleep 2
        ;;
      *) return "$status" ;;
    esac
  done
}

OK=0
DOWNLOADED=0
REUSED=0
for index in "${SELECTED[@]}"; do
  id="${IDS[$index]}"; target="$OUTPUT/${PATHS[$index]}"; expected="${HASHES[$index]}"
  check_target "$target"
  check_target "$target.sha256"
  if [ -f "$target" ]; then
    if [ "$expected" = - ]; then expected="$(receipt_hash "$target")"; fi
    actual="$(hash_file "$target")"
    [ "$actual" = "$expected" ] || die "已有资源 SHA-256 校验失败，原文件已保留；请审核并移走后重试：$target"
    if [ "$MODE" = download ]; then write_receipt "$target" "$actual"; fi
    REUSED=$((REUSED + 1))
    printf 'OK 已校验：%s\n' "$target"
  else
    [ "$MODE" != verify ] || die "缺少资源：$target"
    mkdir -p -- "$(dirname -- "$target")" || die "无法创建资源目录：$target"
    check_target "$target"
    PART="$(mktemp "$target.part.XXXXXXXX")" || die "无法创建下载临时文件：$target"
    printf '下载：%s [%s]\n' "$id" "${VERSIONS[$index]}"
    if ! download_file "$PART" "${URLS[$index]}"; then
      die "下载失败：${id}（${URLS[$index]}）；未替换目标文件。"
    fi
    actual="$(hash_file "$PART")"
    if [ "$expected" != - ]; then
      [ "$actual" = "$expected" ] || die "下载资源 SHA-256 与上游清单不符：${id}；未保存为正式资源。"
    else
      printf '提示：%s 无上游 SHA-256，本地记录仅供之后检查文件是否变化。\n' "$id"
    fi
    chmod 644 "$PART" || die "无法设置资源读取权限：$target"
    check_target "$target"
    # -n 防止下载期间其他进程或人工放入同名文件时被覆盖。
    mv -n -- "$PART" "$target" || die "无法保存资源：$target"
    [ ! -e "$PART" ] || die "下载期间目标文件已出现，已保留原文件：$target"
    PART=""
    write_receipt "$target" "$actual"
    DOWNLOADED=$((DOWNLOADED + 1))
    printf 'OK 已保存：%s\n' "$target"
  fi
  OK=$((OK + 1))
done
printf '资源完成：OK %s；下载 %s；复用/校验 %s。\n' "$OK" "$DOWNLOADED" "$REUSED"
