# 资源准备与使用

维护者可以在 Windows 或 macOS 上，把官方原包集中准备到 `resources/`，再打包并启动内网下载服务。服务端只需 Python 3.8+ 标准库，不依赖 Bash；成员安装客户端仍面向 macOS。JDK 和 Gradle 的团队版本保持 **JDK 8（1.8）、Gradle 4.5.1**。

## 清单范围

| 分组 | 固定资源 | 架构与使用方式 |
| --- | --- | --- |
| `runtime` | Azul Zulu JDK 8u504+1、Gradle 4.5.1 | JDK 分 arm64/x64；Gradle 共用。菜单 `1` 一键修复，或 `2` / `7` 分别独立安装 SDK 并配置完整变量 |
| `software` | IDEA Community 2024.3.7.1、DBeaver Community 26.2.2 | 各有 arm64/x64 DMG；IDEA 用菜单 `8` 安装到个人应用目录，DBeaver 用菜单 `6` 下载后手动安装 |
| `plugins` | Database Navigator 4.1.0.3、MyBatisX 1.7.6、GenerateAllSetter 2.8.5、GsonFormatPlus 1.6.1、Key Promoter X 2026.1.2 | 通用 ZIP；菜单 `9` 安装并验证全部插件，或 `6` 下载后从 IDEA 磁盘安装 |

以 [resources/catalog.tsv](../../resources/catalog.tsv) 为下载依据。全部 12 项约 2.53 GB；发布时还需容纳 `dist/server/resources/` 中的副本。Docker Desktop 仅保留[官方下载与许可说明](runtime-sources.md#docker-desktop仅登记暂不自动下载)，不自动下载。Spring Boot Helper 为收费插件，原 Spring Assistant 不兼容目标 IDEA，均不纳入默认清单；研究中记录的 Spring Boot Assistant 替代项也未加入本次下载。

版本、官方直链、系统支持范围及校验依据见[运行环境与桌面工具来源](runtime-sources.md)、[IDEA 与插件来源](plugin-sources.md)。来源核验、文件下载、目标电脑安装和业务构建验收是不同步骤，不应互相替代。

## 维护者准备文件

在项目根目录执行。下例为 macOS，Windows 将 `python3` 替换为 `py -3`，或已确认是 Python 3.8+ 的 `python`：

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

已有且校验通过的资源会复用。校验不符时保留原文件并停止，由维护者检查后移走异常文件再重试；不要仅为了让校验通过而修改摘要。有官方 SHA-256 的 JDK、Gradle、IDEA、DBeaver 使用清单中的固定值。五个插件的官方元数据未提供独立 SHA-256，清单记为 `-`，首次下载时生成同名 `.sha256` 本地记录，后续用它检查文件是否变化；这不等于官方发布了该摘要。保留原始 ZIP、DMG、许可证及校验文件。

## 发布到内网

完成全部资源准备与校验后执行：

```bash
python3 server/manage.py package --server "192.168.1.20:8080" --scheme http --with-resources --output dist/server
python3 server/manage.py serve --directory dist/server --bind 0.0.0.0 --port 8080
```

资源放到 `dist/server/resources/`，不放进 `start.zip` 或 `team-dev-env.zip`。使用其他本地资源目录时，再加 `--resources-dir /absolute/path/team-resources`；该目录须包含 `catalog.tsv`、清单内全部资源和所需的本地校验记录。

只更新成员脚本时省略 `--with-resources`，保留输出目录已有资源，不必重复复制或上传大包。打包仍会根据本地完整资源库校验并生成成员清单，因此应保留本地 `resources/`。成员清单包含确定的文件摘要，成员下载时据此核对；插件的摘要仍来自维护者首次下载的本地记录。打包不等于发布服务器，上传步骤见[内网分发指南](../distribution.md)。

Windows 用 `py -3` 执行同样的 `package` / `serve`，也可用 `server/start-server.cmd`；Mac 原生入口为 `server/start-server.command`。无参入口仅托管已打包目录，默认 `127.0.0.1:8080`。`preview` 可组合打包与本机服务，默认 8081，并在端口占用时先退出。打包地址与协议按命令行、环境变量、JSON 配置、安全字面默认值的顺序确定，详见[服务启动与配置](../service-startup.md)。当前没有 Windows 实机验收结果。

## 成员下载和安装

1. 从团队内网下载并解压 `start.zip`，双击「开始配置.command」。
2. 菜单 `1` 可一键修复和复验 SDK、完整变量、IDEA 及插件。有业务项目时，先用菜单 `3` 选择项目；修复后必须通过真实 Gradle `build` 才报告整体成功。未选项目时会明确说明未执行构建。
3. 单独安装 IDEA 可选菜单 `8`，校验后安装到 `~/Applications/IntelliJ IDEA CE.app`；菜单 `9` 安装并验证全部 IDEA 插件，菜单 `10` 查看修复历史。
4. 只需下载安装包、DBeaver 或插件时选择 `6`，文件保存到 `~/Downloads/team-java-env/` 下的对应子目录。DBeaver 打开 DMG 手动安装；插件也可在 IDEA 的 `Settings → Plugins → 齿轮 → Install Plugin from Disk` 中选原始 ZIP，**无需解压**。

菜单 `6` 只保存文件；安装和复验结果以对应安装菜单为准。IDEA 的个人目录 `~/Applications` 与系统 `/Applications` 不同，工具自动识别当前用户，无需填写用户名。手动安装时，在 Finder 按 `Command + Shift + G` 前往 `~/Applications`（没有则先创建），复制 DMG 中的 `IntelliJ IDEA CE.app`，不使用通常指向系统目录的 `Applications` 快捷方式。完整步骤见 [IDE 指南](../environment/ide.md)。独立 JDK / Gradle 及完整变量见[运行环境指南](../environment/runtime.md)；安装 IDEA 后另行设置项目 SDK 和 Gradle JVM。

## 离线范围

此资源目录解决安装包和插件 ZIP 的内网获取，不代表业务项目已能完全断网构建。业务依赖、Gradle 插件及 Maven 仓库缓存须由项目维护者另行准备；DBeaver / Database Navigator 所需 JDBC 驱动、MySQL 容器镜像也未自动缓存。连接团队开发数据库不需要本地 MySQL；需要本地容器时见[本地服务指南](../environment/services.md)。
