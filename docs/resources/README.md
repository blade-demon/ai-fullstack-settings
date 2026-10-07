# 资源准备与使用

维护者可以在 Windows 或 macOS 上，把官方原包集中准备到 `resources/`，再打包并启动内网下载服务。服务端只需 Python 3.8+ 标准库，不依赖 Bash；成员安装客户端仍面向 macOS。一键安装基线保持 **JDK 8（1.8）、Gradle 4.5.1**，Gradle 单独安装另可选择 **6.8**。

## 清单范围

| 分组 | 固定资源 | 架构与使用方式 |
| --- | --- | --- |
| `runtime` | Azul Zulu JDK 8u504+1、Gradle 4.5.1 / 6.8 | JDK 分 arm64/x64；Gradle 共用。菜单 `1` 固定 JDK 8 + Gradle 4.5.1，`2` 单独安装 JDK 8，`3.1` / `3.2` 分别安装两版 Gradle |
| `software` | IDEA Community 2024.3.7.1、DBeaver Community 26.2.2 | 各有 arm64/x64 DMG；IDEA 用菜单 `4` 安装到个人应用目录，DBeaver 由维护者命令行下载后手动安装 |
| `plugins` | Database Navigator 4.1.0.3、MyBatisX 1.7.6、GenerateAllSetter 2.8.5、GsonFormatPlus 1.6.1、Key Promoter X 2026.1.2、Lombok 243.28141.18 | 通用 ZIP；菜单 `5` 安装并验证全部插件，或由维护者命令行下载后从 IDEA 磁盘安装 |

以 [resources/catalog.tsv](../../resources/catalog.tsv) 为下载依据。现共 24 项（原有 14 项、前端工具 10 项）；Gradle 6.8 已于 2026-10-07 下载并通过固定摘要校验，分发前仍须核对全部资源。完整资源大小以实际下载为准；发布时还需容纳 `dist/server/resources/` 中的副本。Docker Desktop 仅保留[官方下载与许可说明](runtime-sources.md#docker-desktop仅登记暂不自动下载)，不自动下载。Spring Boot Helper 为收费插件，原 Spring Assistant 不兼容目标 IDEA，均不纳入默认清单；研究中记录的 Spring Boot Assistant 替代项也未加入本次下载。

版本、官方直链、系统支持范围及校验依据见[运行环境与桌面工具来源](runtime-sources.md)、[IDEA 与插件来源](plugin-sources.md)。来源核验、文件下载、目标电脑安装和业务构建验收是不同步骤，不应互相替代。

## 默认：一键准备并启动

先按[Python 3 安装指引](../service-startup.md#部署前安装-python-3)在实际运行下载服务的机器上安装并验证，再在项目根目录执行。下例为 macOS，Windows 将 `python3` 替换为 `py -3`，或已确认是 Python 3.8+ 的 `python`：

```bash
python3 server/manage.py start
```

也可双击 `server/start-server.command`（macOS）或 `server/start-server.cmd`（Windows），无参入口默认执行 `start`。它检测本机活动 IPv4 地址，多候选时选择序号；先绑定 `0.0.0.0:8080`，再按清单校验已有资源、下载缺失项、带资源打包到 `dist/server`，最后显示实际 HTTP 下载链接。保持窗口运行，并从成员电脑验证地址、防火墙及 VPN 是否允许访问。

资源默认保存在 `resources/`，重复启动会复用校验通过的文件；损坏资源会保留并报错，不自动覆盖。可用 `--server` 覆盖自动选址，或用 `--port`、`--output`、`--resources-dir`、`--catalog` 自定义端口、发布目录、资源库和清单。IP 变化后重新 `start`，让成员重新下载启动包。完整参数、重启方式与配置说明见[服务启动指南](../service-startup.md)。

## 高级：单独准备或校验文件

需要提前下载资源、分组准备或在不同机器上部署时，单独使用 `prepare`：

```bash
python3 server/manage.py prepare --dry-run
python3 server/manage.py prepare
python3 server/manage.py prepare --verify
```

默认读取 `resources/catalog.tsv`，保存到 `resources/`。可以缩小范围：

```bash
# 只准备运行环境
python3 server/manage.py prepare --group runtime

# 只准备 Apple Silicon 所需软件；架构筛选同时包含 any 通用资源
python3 server/manage.py prepare --group software --arch arm64

# 只准备某个插件
python3 server/manage.py prepare --id mybatisx

# 保存到其他本地目录
python3 server/manage.py prepare --output /absolute/path/team-resources
# 若要直接从该目录打包，同时保存下载清单
cp resources/catalog.tsv /absolute/path/team-resources/catalog.tsv
```

自定义目录请换成当前系统的实际路径；Windows 复制清单可用 PowerShell 的 `Copy-Item resources/catalog.tsv "D:\team-resources\catalog.tsv"`。也可使用系统原生入口 `server/start-server.cmd prepare` 或 `server/start-server.command prepare`。既有 Mac `tools/prepare-resources.sh` 保留使用，但 Windows 服务端无需运行它。

`--group` 支持 `runtime`、`software`、`plugins`、`all`；`--arch` 支持 `arm64`、`x64`、`any`、`all`。筛选条件同时生效。`--dry-run` 不联网、不写文件；`--verify` 只校验已存在文件，不下载、不补写校验记录。

已有且校验通过的资源会复用。校验不符时保留原文件并停止，由维护者检查后移走异常文件再重试；不要仅为了让校验通过而修改摘要。有官方 SHA-256 的 JDK、Gradle、IDEA、DBeaver 使用清单中的固定值。六个插件的官方元数据未提供独立 SHA-256，清单记为 `-`，首次下载时生成同名 `.sha256` 本地记录，后续用它检查文件是否变化；这不等于官方发布了该摘要。保留原始 ZIP、DMG、许可证及校验文件。

## 高级：单独打包与托管

完成全部资源准备与校验后执行：

```bash
python3 server/manage.py package --server "192.168.1.20:8080" --scheme http --with-resources --output dist/server
python3 server/manage.py serve --directory dist/server --bind 0.0.0.0 --port 8080
```

资源放到 `dist/server/resources/`，不放进 `start.zip` 或 `team-dev-env.zip`。使用其他本地资源目录时，再加 `--resources-dir /absolute/path/team-resources`；该目录须包含 `catalog.tsv`、清单内全部资源和所需的本地校验记录。

只更新成员脚本时省略 `--with-resources`，保留输出目录已有资源，不必重复复制或上传大包。打包仍会根据本地完整资源库校验并生成成员清单，因此应保留本地 `resources/`。成员清单包含确定的文件摘要，成员下载时据此核对；插件的摘要仍来自维护者首次下载的本地记录。打包不等于发布服务器，上传步骤见[内网分发指南](../distribution.md)。

Windows 用 `py -3` 执行同样的 `package` / `serve`，原生入口也可显式传入这些子命令。`serve` 只读托管已有发布目录，不改写包；`preview` 则会重新打包并默认监听本机 `127.0.0.1:8081`，在端口占用时先退出。HTTPS 静态服务或反向代理使用高级打包流程及 `package --scheme https`。地址与协议优先级见[服务启动与配置](../service-startup.md)。当前没有 Windows 实机验收结果。

## 成员下载和安装

1. 从团队内网下载并解压 `start.zip`，双击「开始配置.command」。
2. 保存工作并退出 IDEA，使用菜单 `1` 一键安装、配置和复验 JDK 8、Gradle 4.5.1、完整变量、IDEA 及全部六个推荐插件。菜单不选择业务项目，也不执行构建；菜单 `2` 安装并配置 JDK 8，菜单 `3` 选择 Gradle 版本，也可直接输入 `3.1` / `3.2` 安装 4.5.1 / 6.8。
3. 单独安装 IDEA 可选菜单 `4`，校验后安装到 `~/Applications/IntelliJ IDEA CE.app`；菜单 `5` 安装并验证全部六个推荐 IDEA 插件。日志和修复历史仍保存，可直接打开输出的目录查看。
4. 只需下载软件、DBeaver 或插件时，由维护者在完整工具目录运行 `bash .support/scripts/download-tools.sh` 并选择资源，文件保存到 `~/Downloads/team-java-env/` 下的对应子目录。DBeaver 打开 DMG 手动安装；插件也可在 IDEA 的 `Settings → Plugins → 齿轮 → Install Plugin from Disk` 中选原始 ZIP，**无需解压**。

`download-tools.sh` 仅下载时只保存文件；安装和复验结果以对应安装菜单为准。IDEA 的个人目录 `~/Applications` 与系统 `/Applications` 不同，工具自动识别当前用户，无需填写用户名。手动安装时，在 Finder 按 `Command + Shift + G` 前往 `~/Applications`（没有则先创建），复制 DMG 中的 `IntelliJ IDEA CE.app`，不使用通常指向系统目录的 `Applications` 快捷方式。完整步骤见 [IDE 指南](../environment/ide.md)。独立 JDK / Gradle 及完整变量见[运行环境指南](../environment/runtime.md)；安装 IDEA 后另行设置项目 SDK 和 Gradle JVM。

## 前端工具资源

新增 nvm、Node14 x64、Node16/18 两种架构、iTerm2、Oh My Zsh 和两个外部 Zsh 插件，均已准备并固定 SHA-256，详见[前端资源来源](frontend-sources.md)。使用默认全量准备可同时提供 Apple Silicon 上需要的 Node14 x64 包；单独筛选 arm64 时须另外准备该 ID。前端 shell 插件由独立安装器处理，不属于 IDEA 推荐插件。

## 离线范围

此资源目录解决安装包和插件 ZIP 的内网获取，不代表业务项目已能完全断网构建。业务依赖、Gradle 插件及 Maven 仓库缓存须由项目维护者另行准备；DBeaver / Database Navigator 所需 JDBC 驱动、MySQL 容器镜像也未自动缓存。连接团队开发数据库不需要本地 MySQL；需要本地容器时见[本地服务指南](../environment/services.md)。
