#!/usr/bin/env bash
# 可选的本地数据库；与 JDK/Gradle 静态文件服务器相互独立。
set -euo pipefail

usage() {
  cat <<'EOF'
用法：bash scripts/services/mysql.sh [up|down|status|logs|help] [--dry-run]

  up        后台启动 MySQL；实际执行前必须设置 MYSQL_ROOT_PASSWORD
  down      停止并移除容器和网络，保留数据卷
  status    查看容器状态（包括已停止的容器）
  logs      显示最近 100 行并持续跟随日志；Ctrl+C 退出
  help      显示帮助（默认）
  --dry-run 只展示将执行的命令；不调用 Docker、不写文件、不显示密码

环境变量：
  MYSQL_IMAGE         镜像，默认 mysql:8.0
  MYSQL_PORT          本机端口，默认 3306；仅绑定 127.0.0.1
  MYSQL_DATABASE      首次初始化的数据库，默认 app_dev
  MYSQL_ROOT_PASSWORD 实际 up 时必填；通过环境变量传给 Compose
  MYSQL_PROJECT_NAME  固定项目名，默认 ai-fullstack-mysql
  MYSQL_PLATFORM      可选目标平台，例如 linux/amd64；默认由 Docker 选择

要求：已安装并运行 Docker，且可使用 docker compose。
选择 mysql:5.7 时，请自行确认镜像架构和模拟运行兼容性；脚本不自动改平台。
数据保存在命名卷中；已有数据卷不会因修改初始化密码或数据库名而重新初始化。
同一实例的后续命令应保持相同 MYSQL_PROJECT_NAME。
EOF
}

fail_usage() {
  printf '错误：%s\n' "$1" >&2
  exit 2
}

action=''
dry_run=false
for argument in "$@"; do
  case "$argument" in
    --dry-run) dry_run=true ;;
    -h|--help|help)
      [ -z "$action" ] || fail_usage '只能指定一个操作。'
      action=help
      ;;
    up|down|status|logs)
      [ -z "$action" ] || fail_usage '只能指定一个操作。'
      action="$argument"
      ;;
    *) fail_usage "未知参数：${argument}；请使用 help 查看用法。" ;;
  esac
done
action="${action:-help}"
if [ "$action" = help ]; then
  usage
  exit 0
fi

script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(CDPATH= cd -- "$script_dir/../.." && pwd)"
compose_file="$project_root/config/mysql.compose.yaml"
[ -f "$compose_file" ] || fail_usage "找不到配置文件：$compose_file"
source "$project_root/config/env.sh"

export MYSQL_IMAGE="${MYSQL_IMAGE:-mysql:8.0}"
export MYSQL_PORT="${MYSQL_PORT:-3306}"
export MYSQL_DATABASE="${MYSQL_DATABASE:-app_dev}"
export MYSQL_PLATFORM="${MYSQL_PLATFORM:-}"
export MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-}"
project_name="${MYSQL_PROJECT_NAME:-ai-fullstack-mysql}"

case "$MYSQL_PORT" in
  *[!0-9]*|'') fail_usage 'MYSQL_PORT 必须是 1 到 65535 之间的整数。' ;;
esac
if [ "${#MYSQL_PORT}" -gt 5 ] || ((10#$MYSQL_PORT < 1 || 10#$MYSQL_PORT > 65535)); then
  fail_usage 'MYSQL_PORT 必须是 1 到 65535 之间的整数。'
fi
if ! [[ "$project_name" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
  fail_usage 'MYSQL_PROJECT_NAME 只能包含小写字母、数字、短横线和下划线，并以字母或数字开头。'
fi

# 固定项目名与绝对路径使调用位置无关；不自动加载调用目录中的 .env。
command_args=(docker compose --project-name "$project_name"
  --project-directory "$project_root" --env-file /dev/null --file "$compose_file")
case "$action" in
  up) command_args+=(up --detach mysql) ;;
  down) command_args+=(down) ;;
  status) command_args+=(ps --all) ;;
  logs) command_args+=(logs --follow --tail 100 mysql) ;;
esac

if [ "$dry_run" = true ]; then
  printf '预演：不执行 Docker，不写文件；密码通过环境变量读取，不会显示。\n'
  if [ "$action" = up ] && [ -z "$MYSQL_ROOT_PASSWORD" ]; then
    printf '实际启动前请设置非空的 MYSQL_ROOT_PASSWORD。\n'
  fi
  printf '将执行：'
  # Bash 3.2 的 %q 在部分 UTF-8 locale 下会拆分中文字符，改用单引号转义。
  single_quote="'"
  escaped_single_quote="'\\''"
  for argument in "${command_args[@]}"; do
    printf "'%s' " "${argument//$single_quote/$escaped_single_quote}"
  done
  printf '\n'
  exit 0
fi

if [ "$action" = up ] && [ -z "$MYSQL_ROOT_PASSWORD" ]; then
  fail_usage '启动前必须设置非空的 MYSQL_ROOT_PASSWORD；可先使用 up --dry-run 查看命令。'
fi
if ! command -v docker >/dev/null 2>&1; then
  printf '错误：未找到 Docker；请先安装并启动 Docker。\n' >&2
  exit 127
fi
if ! docker compose version >/dev/null 2>&1; then
  printf '错误：Docker Compose 不可用；请确认 docker compose 可以运行。\n' >&2
  exit 1
fi

exec "${command_args[@]}"
