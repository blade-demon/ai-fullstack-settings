# 可直接修改冒号后的默认值，也可在运行命令前通过环境变量覆盖。
# 本文件是 Bash 配置，只加载可信内容。包名是内网分发约定，可按实际文件修改。
team_config="$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)/team.sh"
if [ -f "$team_config" ]; then source "$team_config"; fi
unset team_config
SERVER_ADDR="${SERVER_ADDR:-127.0.0.1:8080}"
SERVER_SCHEME="${SERVER_SCHEME:-http}"
JDK_PACKAGE_PATH="${JDK_PACKAGE_PATH:-}"
JDK_SHA256="${JDK_SHA256:-}"
JDK_AUTO_DETECT="${JDK_AUTO_DETECT:-true}"
JDK_INSTALL_DIR="${JDK_INSTALL_DIR:-$HOME/.local/share/java-dev/jdk8}"
ENV_FILE="${ENV_FILE:-$HOME/.config/java-dev/env.sh}"
JDK_ENV_FILE="${JDK_ENV_FILE:-${ENV_FILE%/*}/jdk.sh}"
GRADLE_ENV_FILE="${GRADLE_ENV_FILE:-${ENV_FILE%/*}/gradle.sh}"
SHELL_PROFILE="${SHELL_PROFILE:-}"
GRADLE_VERSION="${GRADLE_VERSION:-4.5.1}"
GRADLE_PACKAGE_PATH="${GRADLE_PACKAGE_PATH:-resources/runtime/gradle/gradle-${GRADLE_VERSION}-bin.zip}"
GRADLE_SHA256="${GRADLE_SHA256:-}"
GRADLE_INSTALL_DIR="${GRADLE_INSTALL_DIR:-$HOME/.local/share/java-dev/gradle-${GRADLE_VERSION}}"
GRADLE_USER_HOME="${GRADLE_USER_HOME:-$HOME/.gradle}"
GRADLE_BUILD_TASK="${GRADLE_BUILD_TASK:-build}"
IDEA_VERSION="${IDEA_VERSION:-2024.3.7.1}"
IDEA_APP="${IDEA_APP:-$HOME/Applications/IntelliJ IDEA CE.app}"
IDEA_PLUGINS_DIR="${IDEA_PLUGINS_DIR:-$HOME/Library/Application Support/JetBrains/IdeaIC2024.3/plugins}"
REPAIR_HISTORY_DIR="${REPAIR_HISTORY_DIR:-$HOME/Library/Logs/team-java-env/history}"

# 可选本地数据库的团队默认值；不在分发文件中保存 MYSQL_ROOT_PASSWORD。
export MYSQL_IMAGE="${MYSQL_IMAGE:-mysql:8.0}"
export MYSQL_PORT="${MYSQL_PORT:-3306}"
export MYSQL_DATABASE="${MYSQL_DATABASE:-app_dev}"
export MYSQL_PROJECT_NAME="${MYSQL_PROJECT_NAME:-ai-fullstack-mysql}"
export MYSQL_PLATFORM="${MYSQL_PLATFORM:-}"
