# 前端转型 AI 全栈计划

为团队维护一套 macOS 开发环境工具，一键安装基线为 **JDK 8、独立安装的 Gradle 4.5.1、IDEA 2025.3.6.1 开源社区版和六个配套插件**，Gradle 另可选择 6.8。成员菜单先只读扫描，再安装、配置、验证并保存历史；项目检查和构建验证由维护者通过命令行执行。团队学习安排见[转型推进方案](docs/roadmap.md)。

## 小组成员开始使用

1. 连接团队内网，下载维护者提供的 **`start.zip`**，解压并双击 **「开始配置.command」**。入口下载、校验完整工具后打开菜单，先显示环境扫描结果。
2. 保存工作并退出 IDEA，然后用方向键选择 **「一键安装 Java 环境」**，按 Enter 查看并确认操作。它固定处理 JDK 8、独立 Gradle 4.5.1、IDEA 和全部六个插件，检查完整持久化环境变量；已验证的同版安装会复用。
3. 查看最终环境验证结果和显示的历史目录。菜单不选择业务项目，也不执行项目构建；安装结果会明确显示**未执行项目构建**。
4. 新开终端使环境配置生效；打开 IDEA 后按 [IDE 指南](docs/environment/ide.md)确认 Project SDK、Gradle JVM 和分发设置，并执行 Gradle 同步。业务项目另行验证；静态配置可解析及终端构建通过均不代表 GUI 同步成功。

启动包同时包含「开始配置.command」和「卸载环境.command」。需要卸载时双击后者，先选择是否删除 IDEA；选择删除后，默认一并删除配置、SDK 登记和用户插件，只有在保留提示中输入 `y` / `yes` 才保留。核对删除清单并输入 `DELETE` 后才执行；缓存、日志和 Local History 默认保留。已有成员须重新下载一次 `start.zip` 才能获得这个入口。详见[卸载指南](docs/environment/cleanup.md)。

成员无需克隆仓库、填写服务器地址，也无需预装 Python 或 Homebrew。Java 安装不要求 Git；Oh My Zsh 框架需要可用 Git，缺少时工具会提示处理，不自动安装 Xcode 开发工具。工具使用个人目录，不使用 `sudo`，不自动结束 IDEA 进程。业务项目由团队另行提供；仅使用本地 MySQL 时才需要 Docker。

下表编号对应 `--plain` 普通模式；默认 Go TUI 提供同名操作，用方向键和 Enter 选择。

| 菜单 | 操作 |
| --- | --- |
| `1` | 一键安装 JDK、Gradle 并配置环境，固定 JDK 8 + Gradle 4.5.1，包含 IDEA 和全部六个插件 |
| `2` | 安装并配置 JDK 8 |
| `3` | 安装并配置 Gradle；`3.1` Gradle 4.5.1、`3.2` Gradle 6.8 |
| `4` | 安装 IDEA 软件；菜单显示当前用户 `$HOME/Applications` 的实际路径 |
| `5` | 安装推荐 IDEA 插件（全部六个），执行前须退出 IDEA |
| `6` | 独立前端环境：nvm / Node 14、16、18、iTerm2、Oh My Zsh 与四个常用插件 |
| `0` | 退出 |

普通模式主菜单可直接输入 `3.1` / `3.2`，也可输入 `3` 进入 Gradle 版本选择；子菜单可输入 `1` / `2` 或完整编号选择版本，输入 `0` 返回，空行不开始安装。两版 Gradle 均使用 JDK 8，安装时会检查并补齐 JDK 8 环境。

启动扫描保持只读，不开始下载、安装或业务构建。项目检查、仅下载、历史查看和可选 MySQL 服务保留为维护者命令行功能。看到文件、版本参考或 Wrapper 缓存，不等于项目已经构建成功。首次打开的来源确认、备用完整 ZIP 和下载故障见[内网分发指南](docs/distribution.md)。请保留完整工具目录及隐藏的 `.support`。

## 前端环境与 npx

TUI 的“安装前端环境”页面（普通模式菜单 `6`）提供独立前端环境安装；原 Java 一键范围保持不变。nvm 管理固定 Node 14.21.3 / 16.20.2 / 18.20.8，iTerm2 安装到个人 Applications，Oh My Zsh 启用 git、z、zsh-autosuggestions、zsh-syntax-highlighting 并保留已有配置。Node 14 在 Apple Silicon 上要求已有 Rosetta；iTerm2 3.7.3 要求 macOS 13+。

`npm-cli/` 提供临时 npm 包 `team-dev-env-preview`，可本地 `npm pack` 后通过 npx 运行，正式包名确定前保持 private。npx 需要已有 Node/npm；首次无 Node 的电脑继续用双击入口。完整命令、维护状态、配置备份和边界见[前端环境指南](docs/environment/frontend.md)。交互界面已迁移到 Go + Bubble Tea，npx 继续作为薄启动入口；参数化 CLI 和 `--plain` 保留，详见[TUI 指南](docs/environment/tui.md)。

## 安装位置与完整环境

IDEA 和 iTerm2 统一安装到当前用户的 `/Users/用户名/Applications`。脚本从当前 `HOME` 解析该目录，`~/Applications` 是它的简写；不会在用户主目录下再创建 `Users/用户名`，也不安装到系统 `/Applications`。

IDEA 使用 JetBrains GitHub 发布的 **2025.3.6.1 Community Open Source** 原包；2024 已从有效下载清单和新安装基线移除。已有 2024 应用不会被静默覆盖，须先按[卸载指南](docs/environment/cleanup.md)核对并确认卸载，再安装 2025。官方来源及插件兼容依据见[来源记录](docs/resources/plugin-sources.md)。

| 项目 | 默认位置或配置 |
| --- | --- |
| JDK 8 | `~/.local/share/java-dev/jdk8`；复用已有 JDK 时以实际 `JAVA_HOME` 为准 |
| 独立 Gradle | `~/.local/share/java-dev/gradle-4.5.1` 或 `~/.local/share/java-dev/gradle-6.8`，按版本分别保存 |
| Gradle 用户缓存 | `~/.gradle`，可通过 `GRADLE_USER_HOME` 指定 |
| IDEA | `~/Applications/IntelliJ IDEA CE.app`，不是系统 `/Applications` |
| IDEA 配置 | `~/Library/Application Support/JetBrains/IdeaIC2025.3`，可通过 `IDEA_CONFIG_DIR` 指定 |
| IDEA JDK 8 名称 | `azul-1.8`，可通过 `IDEA_JDK_NAME` 指定；与实际安装路径分别管理 |
| IDEA 插件 | `~/Library/Application Support/JetBrains/IdeaIC2025.3/plugins` |
| 受管环境 | `~/.config/java-dev/jdk.sh`、`gradle.sh`，由同目录 `env.sh` 聚合加载 |

JDK 配置包含 `JAVA_HOME`、`JAVA_8_HOME`、`JRE_HOME`，其中 `JRE_HOME` 指向实际 `$JAVA_HOME/jre`。`GRADLE_HOME` 指向最近选择的 Gradle，保留已配置的 `GRADLE_4_5_1_HOME` / `GRADLE_6_8_HOME` 版本别名，并配置 `GRADLE_USER_HOME`。聚合环境把 Java 和 Gradle 的 `bin` 放在 `PATH` 前部并去重，不设置全局 `CLASSPATH`。

脚本保留环境文件和 Shell 配置中的用户内容，只更新受管区块；首次改写已有文件时保存同路径 `.bak`。重复修复相同内容不会反复追加配置。详细路径、备份和加载方式见[运行环境指南](docs/environment/runtime.md)，独立安装与真实构建见[Gradle 指南](docs/environment/gradle.md)。

## 修复结果与历史

每次开始修复后，成功或失败都会保存独立记录，默认位于：

```text
~/Library/Logs/team-java-env/history/<本次记录>/
├── report.md                # 结果、阶段摘要及变更说明
├── steps.tsv                # 每个阶段的状态、退出码和日志位置
├── result.tsv               # 最终状态、退出码、范围及项目
├── logs/                    # SDK、IDEA、插件、构建等阶段输出
├── before/、after/          # 前后配置快照
├── config-changes.diff      # 受管环境与 IDEA SDK 相关字段差异
└── plugin-backups/          # 若替换插件，保存对应原目录
```

历史可直接在上述目录查看，或由维护者运行 `history.sh`，文件用途见[修复历史指南](docs/repair-history.md)。报告同时保留前后扫描与文件摘要；执行插件阶段时另有逐项结果。`--dry-run` 只预览，不安装、不构建，也不创建修复历史。失败后先看 `report.md` 和失败阶段日志，不要因某一步显示“复制完成”或 `--version` 成功就认定整体完成。

菜单操作只报告无项目的环境或组件验证结果。维护者使用 `--project` 时，`SUCCEEDED` 只表示所选修复、SDK 与终端构建验证通过，IDEA 静态配置可解析；仍需手动启动 IDEA 并同步。IDEA 项目预检待配置以阶段退出码 `2` 记录；SDK 与终端构建通过时，总体退出码仍为 `0`，结果为 `PROJECT_BUILD_VERIFIED_IDEA_PENDING`，不会宣称 GUI 已可用。

历史包含配置快照，可能带有原有私有设置。向维护者提供日志前，应检查并去除密码、令牌等敏感内容。

## 维护者准备分发

服务端支持 Windows 和 macOS，需要 Python 3.8+。首次部署时，先在运行脚本的维护者电脑或服务器上按[Python 3 安装指引](docs/service-startup.md#部署前安装-python-3)完成安装与验证；服务端只使用标准库，无需安装第三方 Python 包。

Windows 或 macOS 下载服务器正常拉取仓库后，继续使用原来的 `start` 命令即可。它优先复用校验通过的 `resources/tui/` 和 `resources/cleanup/`；缺失、损坏或与当前源码不匹配时，按已提交的 `resources/runtime-lock.json` 自动下载并校验匹配的运行文件。首次缺少运行文件时需要访问 GitHub Release 或团队镜像，缓存齐全后可离线使用；服务器无需安装 Go、PyInstaller，也无需人工传入 ZIP。

只有维护者修改 Go 或卸载源码后，才需要在 Mac 上重新构建相应产物，确认两套产物均有效，再生成并上传匹配的运行文件 Release，将锁文件与源码配套提交。完整步骤见[运行文件发布指南](docs/environment/runtime-release.md)；目前没有 CI 自动构建或上传。

在**实际运行下载服务的机器**上，进入项目根目录执行；Windows 把下方 `python3` 换成 `py -3`：

```bash
python3 server/manage.py start
```

也可双击 macOS 的 `server/start-server.command` 或 Windows 的 `server/start-server.cmd`。`start` 自动检测本机活动 IPv4 地址；多个候选时按提示选择序号。它先占用默认的 `8080` 端口，再依次完成 `[1/3]` 运行文件与 SDK 资源准备、`[2/3]` 打包到 `dist/server`、`[3/3]` 启动下载服务。就绪输出包含实际 Go TUI 发布版本、带版本参数的 `start.zip?v=go-tui-…` 链接和 `release.json`。保持窗口运行，从成员电脑验证链接后再分发。

**`git pull` 更新源码，不会更新已存在的发布目录或正在运行的服务。** 更新后应停止自己管理的旧服务，再运行 `start`。端口占用时，本次启动不会结束已有进程或改写旧包，已有地址可能仍提供旧版本；只有确认发布物已验证为本次预期版本后才能复用该地址。

重复运行会复用校验通过的资源；24 项 SDK、软件和插件安装资源损坏时会保留并报错，运行文件则由锁定下载流程补齐。安装资源默认保存在 `resources/`，发布副本位于 `dist/server/resources/`，大包不进入启动 ZIP 或完整工具 ZIP。清单现含 24 项（原有 14 项及前端工具 10 项）；Gradle 6.8 已下载并通过固定摘要校验，正式分发时仍会核验本地资源。分组下载与摘要说明见[资源准备指南](docs/resources/README.md)。

只准备运行文件可用 `python3 server/manage.py prepare-runtimes`，加 `--offline` 仅校验本地且不写入。内网镜像用 `--runtime-base-url "http://镜像地址/目录"` 或 `server/config.json` 的 `runtime_base_url` 指定，该目录须提供 `team-dev-env-runtimes.zip`，下载仍须满足仓库锁定的大小与摘要。高级 `package` 始终只校验和打包，不联网；`serve` 启动前校验 `release.json` 及六个发布文件，拒绝缺少新版清单的旧包或损坏包。

`start` 监听 `0.0.0.0`，自动选址不保证能穿过防火墙或 VPN；显式地址和端口可用 `start --server "192.168.1.20" --port 8080` 指定。IP 变化后重新 `start`，并让成员重新下载启动包。`127.0.0.1` 只指向成员自己的电脑，不可作为团队下载地址。停止、重启、参数，以及分机器部署或 HTTPS 所需的高级分步流程见[服务启动指南](docs/service-startup.md)；发布结构和更新要求见[内网分发指南](docs/distribution.md)。

## 维护者命令行

以下示例在仓库根目录运行，下载阶段需要已配置的团队地址与固定摘要清单；成员通常直接使用菜单。

```bash
# 一键修复预览；不修改文件或执行构建
bash install_env.sh --project "/absolute/path/to/java-project" --dry-run

# 一键修复，包含六个插件；执行前保存工作并退出 IDEA
bash install_env.sh --project "/absolute/path/to/java-project"

# 安装 Gradle 6.8，并检查和补齐 JDK 8 环境
bash dev-kit/.support/scripts/repair-env.sh --scope gradle --gradle-version 6.8

# 只读检查指定业务项目及环境，不执行构建
bash dev-kit/.support/scripts/check-env.sh --project "/absolute/path/to/java-project"

# 未选择项目：安装并验证独立 Gradle、补齐 SDK 环境，不执行构建
bash dev-kit/.support/scripts/runtime/install-gradle.sh

# 单独执行项目构建验证
bash dev-kit/.support/scripts/runtime/verify-gradle.sh --project "/absolute/path/to/java-project"

# 只读检查 IDEA 项目配置；不会修改配置或启动 GUI
bash dev-kit/.support/scripts/check-idea-project.sh --project "/absolute/path/to/java-project"

# 单独统一 SDK 登记和所选项目引用；执行前保存工作并退出 IDEA
bash dev-kit/.support/scripts/runtime/config-idea-sdk.sh --project "/absolute/path/to/java-project"

# 在当前终端加载已生成环境；自定义 ENV_FILE 时替换路径
source "$HOME/.config/java-dev/env.sh"

# 查看历史
bash dev-kit/.support/scripts/history.sh

# 仅下载软件或插件；使用已打包工具中的资源清单
bash dev-kit/.support/scripts/download-tools.sh --list
bash dev-kit/.support/scripts/download-tools.sh --id lombok

# 预览可选 MySQL 服务；实际启动要求 Docker 和 MYSQL_ROOT_PASSWORD
bash dev-kit/.support/scripts/services/mysql.sh up --dry-run

# 维护者隔离测试；成员运行工具不需要 Python
python3 -m unittest discover -s tests -v
```

`repair-env.sh --scope all|jdk|gradle|idea|plugins` 可选择修复范围；`--gradle-version 4.5.1|6.8` 选择 Gradle 版本，默认 `4.5.1`，JDK 固定使用 8。指定 `--project` 时仍需通过实际项目构建，并检查报告中的 IDEA 配置状态。直接调用 SDK 安装脚本适合单项调试；需要完整前后快照和汇总历史时，使用菜单或 `repair-env.sh`。

维护者进行 macOS 实机重装测试前，可运行 `bash tools/uninstall-java-gradle.sh` 进入交互引导，选择是否删除 IDEA 软件、核对清理计划并输入 `DELETE` 确认；确认后请求正常退出 IDEA，再删除软件。退出失败会停止清理。仅预览时加 `--dry-run`，非交互默认也只预览。SDK 仅删除带有效 `.team-java-env-install.json` 来源标记的安装，外部 SDK 与 Gradle 用户配置和缓存均保留。`--include-idea-apps` 仅删除 IDEA 软件，`--include-idea` 同时清理配置和用户插件；系统安装需 `--include-system`，`--remove-caches` 仅额外删除 IDEA 缓存、Local History 和日志。清理不创建配置或插件备份、不自动回滚，只保存操作记录。维护者直接运行源码入口时需要 Python 3.8+；成员使用分发包中的「卸载环境.command」，由包内运行时执行同一份卸载实现，无需 Python。参数与范围限制见[卸载指南](docs/environment/cleanup.md)。

本仓库测试使用临时 HOME、微型 SDK 和模拟项目；这些结果不代表真实业务项目已经构建通过，也不代表 Windows 实机安装已经验证。安装资源不包含业务 Maven/Gradle 依赖缓存、额外 JDBC 驱动或 MySQL 镜像，完全离线构建仍需项目维护者准备并实测。

本次更新仅调整脚本与说明，未执行真实环境重装或 GUI 自动验收。

真实预下载 SDK 的构建成功/失败、插件的临时安装和平台验证边界见[验证记录](docs/verification.md)。

## 主要文档

- [运行环境与持久化配置](docs/environment/runtime.md)
- [独立 Gradle 安装与项目构建](docs/environment/gradle.md)
- [IDEA 与六个插件](docs/environment/ide.md)
- [修复历史与 review](docs/repair-history.md)
- [Python 3 安装、服务器启动与排错](docs/service-startup.md)
- [分发流程](docs/distribution.md)
- [运行文件自动下载与维护者发布](docs/environment/runtime-release.md)
- [全部环境指南](docs/environment/README.md)
