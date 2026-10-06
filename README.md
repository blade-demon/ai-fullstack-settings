# 前端转型 AI 全栈计划

为团队维护一套 macOS 开发环境工具，目标为 **JDK 8、独立安装的 Gradle 4.5.1、IDEA 2024.3.7.1 社区版和六个配套插件**。工具先扫描，再修复、验证并保存历史；选择业务项目后，必须完成终端构建验证，并单独报告 IDEA 项目配置状态。团队学习安排见[转型推进方案](docs/roadmap.md)。

## 小组成员开始使用

1. 连接团队内网，下载维护者提供的 **`start.zip`**，解压并双击 **「开始配置.command」**。入口下载、校验完整工具后打开菜单，先显示环境扫描结果。
2. 有业务项目时，先选 **菜单 `3`**，选择包含 `build.gradle` 或 `build.gradle.kts` 的项目根目录。选择本地 Gradle 时不要求 Wrapper；IDEA 选择 Wrapper 时需有完整可执行的 Wrapper。本工具仓库不能代替业务项目。
3. 保存工作并退出 IDEA，然后选 **菜单 `1` 一键修复**。它修复 JDK、独立 Gradle、IDEA 和全部六个插件，检查完整持久化环境变量；已验证的同版安装会复用。已导入 IDEA 的所选项目会统一 JDK 8 登记与引用名称，默认 `azul-1.8`。
4. 查看最终结果及修复历史。已选项目时，按 IDEA 的 Wrapper 或 LOCAL 分发设置执行终端 `build`；无 IDEA 项目配置时使用受管独立 Gradle 并提示待导入。只有退出码为零且输出包含 `BUILD SUCCESSFUL`，才算构建通过。IDEA 待配置时报告 `PROJECT_BUILD_VERIFIED_IDEA_PENDING`，仍需完成 IDEA 设置；未选项目时明确显示**未执行项目构建**。
5. 新开终端使环境配置生效；打开 IDEA 后按 [IDE 指南](docs/environment/ide.md)确认 Project SDK、Gradle JVM 和分发设置，并执行 Gradle 同步。静态配置可解析及终端构建通过均不代表 GUI 同步成功。

成员无需克隆仓库、填写服务器地址，也无需预装 Python、Homebrew 或 Git。工具使用个人目录，不使用 `sudo`，不自动结束 IDEA 进程。业务项目由团队另行提供；仅使用本地 MySQL 时才需要 Docker。

| 菜单 | 操作 |
| --- | --- |
| `1` | 一键修复全部环境和六个插件；已选项目时完成实际构建验证 |
| `2` | 修复 JDK 8 与完整 JDK 环境变量 |
| `3` | 选择或切换项目，并扫描当前环境 |
| `4` / `5` | 启动 / 停止本地 MySQL；停止保留数据 |
| `6` | 仅下载开发软件或插件，不自动安装 |
| `7` | 修复独立 Gradle 4.5.1；已选项目时强制构建验证 |
| `8` | 修复个人应用目录中的 IDEA |
| `9` | 安装并验证全部六个 IDEA 插件，执行前须退出 IDEA |
| `10` | 查看修复历史 |
| `0` | 退出 |

启动扫描不开始下载、安装或业务构建。已选项目时还会只读检查 IDEA 项目设置，待配置时扫描返回非零状态并打印实际路径与设置入口；不会自动修改 IDEA 配置或打开 GUI。看到文件、版本参考或 Wrapper 缓存，不等于项目已经构建成功。首次打开的来源确认、备用完整 ZIP 和下载故障见[内网分发指南](docs/distribution.md)。请保留完整工具目录及隐藏的 `.support`。

## 安装位置与完整环境

| 项目 | 默认位置或配置 |
| --- | --- |
| JDK 8 | `~/.local/share/java-dev/jdk8`；复用已有 JDK 时以实际 `JAVA_HOME` 为准 |
| 独立 Gradle | `~/.local/share/java-dev/gradle-4.5.1` |
| Gradle 用户缓存 | `~/.gradle`，可通过 `GRADLE_USER_HOME` 指定 |
| IDEA | `~/Applications/IntelliJ IDEA CE.app`，不是系统 `/Applications` |
| IDEA 配置 | `~/Library/Application Support/JetBrains/IdeaIC2024.3`，可通过 `IDEA_CONFIG_DIR` 指定 |
| IDEA JDK 8 名称 | `azul-1.8`，可通过 `IDEA_JDK_NAME` 指定；与实际安装路径分别管理 |
| IDEA 插件 | `~/Library/Application Support/JetBrains/IdeaIC2024.3/plugins` |
| 受管环境 | `~/.config/java-dev/jdk.sh`、`gradle.sh`，由同目录 `env.sh` 聚合加载 |

JDK 配置包含 `JAVA_HOME`、`JAVA_8_HOME`、`JRE_HOME`；Gradle 配置包含 `GRADLE_HOME`、`GRADLE_4_5_1_HOME`、`GRADLE_USER_HOME`。聚合环境把 Java 和 Gradle 的 `bin` 放在 `PATH` 前部并去重，不设置全局 `CLASSPATH`。

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

菜单 `10` 可查看历史，文件用途见[修复历史指南](docs/repair-history.md)。报告同时保留前后扫描与文件摘要；执行插件阶段时另有逐项结果。`--dry-run` 只预览，不安装、不构建，也不创建修复历史。失败后先看 `report.md` 和失败阶段日志，不要因某一步显示“复制完成”或 `--version` 成功就认定整体完成。

`SUCCEEDED` 只表示所选修复、SDK 与终端构建验证通过，IDEA 静态配置可解析；仍需手动启动 IDEA 并同步。IDEA 项目预检待配置以阶段退出码 `2` 记录；SDK 与终端构建通过时，总体退出码仍为 `0`，结果为 `PROJECT_BUILD_VERIFIED_IDEA_PENDING`，不会宣称 GUI 已可用。

历史包含配置快照，可能带有原有私有设置。向维护者提供日志前，应检查并去除密码、令牌等敏感内容。

## 维护者准备分发

服务端支持 Windows 和 macOS，需要 Python 3.8+。首次部署时，先在运行脚本的维护者电脑或服务器上按[Python 3 安装指引](docs/service-startup.md#部署前安装-python-3)完成安装与验证；服务端只使用标准库，无需安装第三方 Python 包。

在**实际运行下载服务的机器**上，进入项目根目录执行；Windows 把下方 `python3` 换成 `py -3`：

```bash
python3 server/manage.py start
```

也可双击 macOS 的 `server/start-server.command` 或 Windows 的 `server/start-server.cmd`。`start` 自动检测本机活动 IPv4 地址；多个候选时按提示选择序号。它先占用默认的 `8080` 端口，再校验已有资源、下载缺失文件、带资源打包到 `dist/server`，最后通过 HTTP 提供下载并显示实际链接。保持窗口运行，从成员电脑验证链接后再分发。

重复运行会复用校验通过的资源；遇到损坏文件会保留并报错。资源默认保存在 `resources/`，发布副本位于 `dist/server/resources/`，大包不进入启动 ZIP 或完整工具 ZIP。分组下载与摘要说明见[资源准备指南](docs/resources/README.md)。

`start` 监听 `0.0.0.0`，自动选址不保证能穿过防火墙或 VPN；显式地址和端口可用 `start --server "192.168.1.20" --port 8080` 指定。IP 变化后重新 `start`，并让成员重新下载启动包。`127.0.0.1` 只指向成员自己的电脑，不可作为团队下载地址。停止、重启、参数，以及分机器部署或 HTTPS 所需的高级分步流程见[服务启动指南](docs/service-startup.md)；发布结构和更新要求见[内网分发指南](docs/distribution.md)。

## 维护者命令行

以下示例在仓库根目录运行，下载阶段需要已配置的团队地址与固定摘要清单；成员通常直接使用菜单。

```bash
# 一键修复预览；不修改文件或执行构建
bash install_env.sh --project "/absolute/path/to/java-project" --dry-run

# 一键修复，包含六个插件；执行前保存工作并退出 IDEA
bash install_env.sh --project "/absolute/path/to/java-project"

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

# 维护者隔离测试；成员运行工具不需要 Python
python3 -m unittest discover -s tests -v
```

`repair-env.sh --scope all|jdk|gradle|idea|plugins` 可选择修复范围；指定 `--project` 时仍需通过实际项目构建，并检查报告中的 IDEA 配置状态。直接调用 SDK 安装脚本适合单项调试；需要完整前后快照和汇总历史时，使用菜单或 `repair-env.sh`。

维护者进行 macOS 实机重装测试前，可运行 `bash tools/uninstall-java-gradle.sh` 进入交互引导，选择是否删除 IDEA 软件、核对清理计划并输入 `DELETE` 确认；确认后请求正常退出 IDEA，再删除软件。退出失败会停止清理。仅预览时加 `--dry-run`，非交互默认也只预览。SDK 仅删除带有效 `.team-java-env-install.json` 来源标记的安装，外部 SDK 与 Gradle 用户配置和缓存均保留。`--include-idea-apps` 仅删除 IDEA 软件，`--include-idea` 同时清理配置和用户插件；系统安装需 `--include-system`，`--remove-caches` 仅额外删除 IDEA 缓存、Local History 和日志。清理不创建配置或插件备份、不自动回滚，只保存操作记录。此工具需要 Python 3.8+，独立于成员菜单和分发；参数与范围限制见[实机清理指南](docs/environment/cleanup.md)。

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
- [全部环境指南](docs/environment/README.md)
