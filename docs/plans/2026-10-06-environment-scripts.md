# 开发环境脚本实施计划

**目标：** 将现有四层环境指南整理成文档、配置、脚本、测试分离的目录，提供 macOS JDK 8 和 Gradle 4.5.1 的安装配置入口。

**设计：** `config/env.sh` 集中管理默认值，环境变量可覆盖；`SERVER_ADDR=127.0.0.1:8080`，默认 HTTP。`scripts/lib/common.sh` 负责配置加载和公共检查；运行时脚本不依赖当前工作目录。JDK 安装到用户目录；Gradle 只修改用户明确传入的现有项目。MySQL 通过独立 Compose 脚本按需启动，IDE 插件继续人工配置。

**约束：** Bash 3.2 兼容；支持空格和中文路径；`--dry-run` 不写文件、不联网；重复执行不重复追加配置；不在本次开发验证中安装真实 JDK 或启动数据库；不生成缺失的 Wrapper JAR。

## 文件与任务

- [x] `tests/test_runtime.py`：先覆盖预演、默认/自定义地址、Gradle 配置更新与备份、失败不破坏现有文件、临时目录 JDK 安装与重复执行，再运行确认未实现时失败。
- [x] `config/env.sh`、`scripts/lib/common.sh`：定义服务器、架构对应安装包名、用户安装目录、Shell 配置文件、Gradle 版本与可选 SHA-256。
- [x] `scripts/runtime/config-jdk.sh`：下载指定架构 tar.gz；校验 SHA-256（提供时）；检查 java/javac 版本；安装到用户目录；生成可重复加载的环境文件并注册至 Shell 配置。
- [x] `scripts/runtime/config-gradle.sh`：接收 `--project`，检查现有 Wrapper 完整性；备份并更新 distributionUrl，保留其余设置；支持 `--dry-run`。
- [x] `install_env.sh`、`scripts/check-env.sh`：统一运行时入口与只读环境诊断；缺少 Wrapper 时在安装之前失败。
- [x] `scripts/services/mysql.sh`、`config/mysql.compose.yaml`：可选 Docker Compose 生命周期管理，绑定本机端口，保留数据卷。
- [x] `README.md`、`docs/environment/*.md`：整理四层指南、服务器文件约定和使用示例，保留转型总纲，移除过期地址与不兼容示例。
- [x] 验收：`bash -n` 检查全部 Shell 文件；Python 标准库集成测试使用临时目录及测试安装包；检查文档链接及目录结构；独立复核脚本。

## 关键验收行为

1. `bash install_env.sh --dry-run` 展示 `http://127.0.0.1:8080`，不创建用户文件。
2. `SERVER_ADDR=mirror.example:9000` 能改变 JDK 与 Gradle 下载地址。
3. Gradle 配置重复运行结果稳定，保留原始备份，Wrapper 缺失时明确失败。
4. 下载或校验失败时不修改用户 Shell 配置，不产生可被误认为有效安装的目录。
5. 数据库停止命令不删除数据卷，帮助及预演不要求 Docker 已安装。

## 验收结果

- 25 项隔离测试通过：13 项运行时与配置测试、12 项 MySQL 入口测试。
- 7 个 Shell 文件通过 macOS Bash 3.2 语法检查；Bash/Zsh 均验证环境文件可加载。
- Markdown 本地链接与代码围栏检查通过；默认服务器与中文路径预演通过。
- 真实 JDK 安装、Gradle 下载/构建和 MySQL 启动未执行，需要实际安装包服务器与业务项目。
