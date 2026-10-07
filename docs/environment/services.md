# 本地服务与数据（维护者可选）

本地 MySQL 是维护者命令行可选服务，不属于成员安装菜单或一键安装范围。先确认业务项目使用的 MySQL 版本。连接团队现有开发库时，可以跳过本地容器；数据库连接信息由项目维护者提供。

当前 `resources/` 提供数据库客户端安装包，没有自动准备 Docker Desktop 或 MySQL 容器镜像。完全离线启动本地数据库前，需要维护者另行准备正确架构、正确版本的镜像并导入 Docker；首次启动时不能假定外网拉取一定可用。

## 使用前准备

先安装并启动团队认可的 Docker Desktop，再使用下方命令行入口。工具不会安装 Docker，配置 JDK 时也不会自动启动数据库。密码通过 `MYSQL_ROOT_PASSWORD` 环境变量传入，不要把密码写入共享脚本、截图或发送给维护者的日志中。

Docker Desktop 的官方入口、系统要求和许可条件见[资源来源说明](../resources/runtime-sources.md#docker-desktop仅登记暂不自动下载)。它不在本次自动下载清单中；需要时使用团队认可的版本与订阅。

本地客户端默认连接 `127.0.0.1:3306`、数据库 `app_dev`，账号为 `root`，密码为首次初始化时提供的值。数据库镜像和连接参数应由维护者按项目要求统一确认。

维护者在 [dev-kit/.support/config/env.sh](../../dev-kit/.support/config/env.sh) 中统一设置 `MYSQL_IMAGE`、端口、数据库名等默认值，再重新打包分发；`mysql.sh` 会使用这些配置，也可通过环境变量覆盖。配置文件不保存 `MYSQL_ROOT_PASSWORD`。

## 维护者命令行

以下命令在仓库根目录执行：

```bash
# 预览容器操作，不需要提供密码
bash dev-kit/.support/scripts/services/mysql.sh up --dry-run

# 已在当前终端安全设置 MYSQL_ROOT_PASSWORD 后启动
bash dev-kit/.support/scripts/services/mysql.sh up

# 查看状态、日志或停止服务
bash dev-kit/.support/scripts/services/mysql.sh status
bash dev-kit/.support/scripts/services/mysql.sh logs
bash dev-kit/.support/scripts/services/mysql.sh down
```

调用 `up` 时需提供非空的 `MYSQL_ROOT_PASSWORD` 环境变量，其他命令不需要密码；避免把密码直接写入会保存到历史记录的命令。`logs` 跟随日志，按 `Ctrl+C` 退出；`down` 停止并移除容器与网络，保留命名数据卷。

| 变量 | 默认值或含义 |
| --- | --- |
| `MYSQL_IMAGE` | `mysql:8.0`，须按公司数据库版本覆盖 |
| `MYSQL_PORT` | `3306`，仅绑定本机 `127.0.0.1` |
| `MYSQL_DATABASE` | `app_dev`，首次初始化创建的库 |
| `MYSQL_PROJECT_NAME` | `ai-fullstack-mysql`，容器服务的项目名称 |
| `MYSQL_PLATFORM` | 可选，按镜像与本机架构需求指定 |

若端口已占用，由维护者调整 `MYSQL_PORT`。同一实例的启动、状态检查和停止需使用相同配置，特别是 `MYSQL_PROJECT_NAME`。

确认选定镜像支持当前机器架构，不要把默认 MySQL 版本当成项目兼容性保证。保留旧数据卷时，修改初始化密码或库名不会自动重置已有数据。[MySQL 官方镜像说明](https://hub.docker.com/_/mysql)

切换 MySQL 大版本时使用新的 `MYSQL_PROJECT_NAME` 隔离数据卷，例如 `ai-fullstack-mysql57`；不要直接让 5.7 与 8.0 共用数据卷。版本升级、迁移及账号管理应遵循团队数据库流程。

## 数据库客户端

维护者在已配置资源清单的工具中运行 `bash dev-kit/.support/scripts/download-tools.sh`，选择适配本机的 DBeaver Community 26.2.2，下载后打开 DMG 并手动安装。在完整工具目录运行时，脚本路径改为 `.support/scripts/download-tools.sh`。文件默认保存在 `~/Downloads/team-java-env/software/dbeaver/`。DBeaver 使用随附运行时，不要强制切换到项目 JDK 8。

按项目配置填写主机、端口、账号与库名，再验证连接。DBeaver 首次连接可能需要下载 JDBC 驱动，当前资源流程没有自动准备驱动缓存；完全离线使用前由维护者补齐并验证。需要 IDEA 内的数据库操作界面时，可安装 Database Navigator，见 [IDE 与插件](ide.md)。

本工具不通过 Homebrew 安装 MySQL；本地服务以团队确认的容器镜像版本为准。
