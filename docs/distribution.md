# 内网分发指南

维护者可在 Windows 或 macOS 上用 Python 3.8+ 准备资源、打包和运行下载服务，服务端不依赖 Bash。小组成员仍使用 macOS 中文安装入口，无需配置服务器地址，也无需安装 Python 或 Homebrew。Java 安装不依赖 Git；Oh My Zsh 框架需可用 Git，缺少时提示处理，不会自动安装系统开发工具。Windows 服务端不代表提供了 Windows 安装客户端。

首次部署前，先在实际运行脚本的电脑或服务器上完成[Python 3 安装与验证](service-startup.md#部署前安装-python-3)。服务端只使用标准库，无需安装第三方 Python 包。Windows 或 macOS 正常拉取仓库后执行原 `start` 即可：已有运行文件校验通过时复用，缺失、损坏或过期时按 `resources/runtime-lock.json` 自动下载匹配的 Go TUI 与卸载工具。首次缺少运行文件时需访问 GitHub Release 或镜像；有效缓存可离线使用。下载服务器无需 Go、PyInstaller 或人工传入运行文件 ZIP，也不会运行 Mac 二进制。

只有维护者修改 Go 或卸载源码后，才需要重新构建、生成并上传匹配的运行文件 Release，将锁文件和源码配套提交；详见[运行文件发布指南](environment/runtime-release.md)。当前没有 CI 自动构建或上传。

**先启动下载服务，再运行成员启动包。** 本机与内网服务器的完整启动命令、停止/重启和端口处理见[服务启动指南](service-startup.md)。打包输出的链接只有在服务启动且根目录配置正确后才能访问。

本次迁移同时更新启动器的终端取消处理。发布后请成员重新下载 `start.zip`；已有 npx 用户也需要使用重新打包后的 npm 包。仅替换服务器上的完整工具包，不能更新成员手里的旧下载模板或 npm 启动代码。

## 成员操作流程

1. 连接团队内网，打开维护者提供的 `start.zip` 下载链接。
2. 解压启动包，可见「开始配置.command」和「卸载环境.command」。安装时双击「开始配置.command」。入口自动下载完整工具、校验 SHA-256、解压；菜单打开时先自动预检现有 JDK 8 和 Gradle 状态。
3. 保存工作并退出 IDEA，用方向键选择「一键安装 Java 环境」，按 Enter 查看并确认操作：固定补齐 JDK 8、独立 Gradle 4.5.1、完整环境变量、IDEA Community Open Source 2025.3.6.1 和全部六个插件，再复验。菜单不选择业务项目，也不执行构建，只报告环境验证结果和“未执行项目构建”。
4. 也可选择「安装并配置 JDK 8」「安装并配置 Gradle」「安装 IDEA 软件」「安装推荐 IDEA 插件」分别处理各组件。IDEA 位于 `~/Applications/IntelliJ IDEA CE.app`，其项目设置见 [IDE 指南](environment/ide.md)。
5. 查看结果和输出的历史目录；新开终端加载环境，再在 IDEA 中导入、配置并同步业务项目。项目检查、构建验证、仅下载及历史查看保留为维护者命令行功能。

卸载时双击独立的「卸载环境.command」，先选择是否删除 IDEA；选择删除后，配置、SDK 登记和用户插件默认一并删除，只有在保留提示中输入 `y` / `yes` 才保留。核对删除计划并输入 `DELETE` 后才执行，缓存、日志和 Local History 默认保留。该入口自带运行时，成员无需安装 Python。卸载范围、无备份说明及取消方式见[卸载指南](environment/cleanup.md)。默认交互为 Go TUI，包含以下同名操作；下表编号供 `--plain` 数字菜单使用：

| 选项 | 操作 |
| --- | --- |
| `1` | 一键安装 JDK、Gradle 并配置环境，固定 JDK 8 + Gradle 4.5.1，包含 IDEA 和全部六个插件 |
| `2` | 安装并配置 JDK 8 |
| `3` | 安装并配置 Gradle；`3.1` Gradle 4.5.1、`3.2` Gradle 6.8 |
| `4` | 安装 IDEA 软件；菜单显示当前用户 `$HOME/Applications` 的实际路径 |
| `5` | 安装推荐 IDEA 插件（全部六个） |
| `6` | 独立前端环境安装，详见[前端指南](environment/frontend.md) |
| `0` | 退出 |

普通模式主菜单可直接输入 `3.1` / `3.2`，也可输入 `3` 进入 Gradle 版本选择；子菜单可输入 `1` / `2` 或完整编号选择版本，输入 `0` 返回，空行不开始安装。两版 Gradle 均使用 JDK 8，安装时会检查并补齐 JDK 8 环境。

启动自动预检保持只读，不下载、安装或构建。扫描结果用于判断待修复项，不代替实际 SDK、完整环境变量、IDEA、插件和项目构建验证。仅有安装包或 Wrapper 缓存，不能代表独立 Gradle 和项目已经就绪。

修复流程先扫描，复用通过验证的已有组件，再补齐缺失内容并检查修复结果。JDK 与 Gradle 安装在成员用户目录，完整变量包括 `JAVA_HOME`、`JAVA_8_HOME`、`JRE_HOME`、`GRADLE_HOME`、已配置的 `GRADLE_4_5_1_HOME` / `GRADLE_6_8_HOME`、`GRADLE_USER_HOME` 及对应 `PATH`。两版 Gradle 使用独立目录，当前 `GRADLE_HOME` 指向最近选择的版本。发生冲突或验证失败时保留原文件并记录失败阶段，不把“安装步骤结束”当作最终成功。

维护者通过 `repair-env.sh --project` 指定已有 IDEA 配置的项目时，会在构建前统一 JDK 8 的 SDK 登记与项目引用名称，默认 `azul-1.8`，可通过 `IDEA_JDK_NAME` 配置。执行前须退出 IDEA；同目录的重复 SDK 名称会合并。尚未导入的项目仍提示待配置，之后完成导入并运行名称同步，见 [IDE 指南](environment/ide.md#统一-jdk-8-登记与项目引用)。

维护者的 `download-tools.sh` 仅下载时把文件保存到 `~/Downloads/team-java-env/` 的对应子目录。「安装 IDEA 软件」（普通模式菜单 `4`）校验 IDEA DMG 后只读挂载，将应用复制到当前用户的 `~/Applications`，无需 `sudo`，不修改系统 `/Applications`，也不自动启动 IDEA。同版本、同 build 且完整的现有应用会复用；其他已有目标保留并报错，不覆盖。手动安装和两个应用目录的区别见 [IDE 指南](environment/ide.md)。

当前 IDEA 原包来自 JetBrains GitHub 的 Community Open Source 2025.3.6.1，默认配置目录为 `IdeaIC2025.3`。2024 已从有效下载清单和新安装基线移除；已有旧应用须先按卸载引导核对并确认删除，再安装 2025。发布时一并更新清单、两架构 DMG 和 Lombok 253.28294.251，来源与摘要见[核验记录](resources/plugin-sources.md)。

工具不下载业务项目，Docker 本次仅登记官方入口，未纳入下载清单。完整工具包 `team-dev-env.zip` 是备用入口：解压后双击 `team-dev-env/开始配置.command`，同样进入菜单；隐藏的 `.support` 必须与入口保持在一起。

「安装并配置 Gradle」（普通模式菜单 `3`）选择 Gradle 4.5.1 / 6.8，安装并配置独立 Gradle，验证版本及变量，不要求提供项目或 Wrapper。维护者通过命令行指定 `--project` 后才执行目标 Gradle 的 `build`（含测试），失败即保留失败结果；需要的企业依赖仓库、网络和权限由团队提供。详细说明见[Gradle 安装指南](environment/gradle.md)。

## 维护者一键准备与启动

在实际运行下载服务的机器上，进入项目根目录执行。以下用 macOS 的 `python3`；Windows 将其替换为 `py -3` 或已确认版本的 `python`：

```bash
python3 server/manage.py start
```

也可双击 Windows 的 `server/start-server.cmd` 或 macOS 的 `server/start-server.command`；无参数时均执行 `start`。它自动检测本机活动 IPv4 地址，多个候选时在终端选择序号；先占用默认 `8080` 端口，再依次执行 `[1/3]` 运行文件与 SDK 资源准备、`[2/3]` 带资源打包、`[3/3]` 下载服务就绪。第一阶段先补齐运行文件，再处理 SDK 下载。就绪时显示真实版本、带版本参数的下载链接和 `release.json` 地址。服务监听 `0.0.0.0`，窗口需要保持运行。自动检测不保证成员网段、防火墙或 VPN 已允许访问，分发前仍须从成员电脑验证。

**拉取源码不等于更新发布目录。** `git pull` 不会改写 `dist/server` 或重启已有服务；正常更新是停止自己管理的旧服务，再运行原 `start`。端口占用时，本次没有更新安装包，已有地址可能仍提供旧版本，工具不会结束占用进程或改写旧包。只有确认已托管文件通过校验且属于本次预期版本，才可复用现有地址。

安装资源下载默认保存到仓库 `resources/`，清单共 24 项，其中原有 14 项和新增前端工具 10 项；原资源包含 JDK 8、Gradle 4.5.1 / 6.8、IDEA 社区版、DBeaver 和六个免费 IDEA 插件。Gradle 6.8 已下载并通过固定摘要校验；正式分发时仍会校验完整资源，下载大小以实际文件为准。重复执行时，已有且校验通过的安装资源会复用；损坏安装资源保留并报错，不自动覆盖。七个运行文件不在这份清单中，由独立的锁定下载流程补齐。来源、版本、分组筛选和校验方式见[资源准备指南](resources/README.md)。

| 参数 | 含义 |
| --- | --- |
| `--server HOST[:PORT]` | 覆盖自动选址，指定成员可访问的主机或 IP，不含协议或路径 |
| `--port PORT` | 默认 `8080`；与显式 `--server` 中的端口不一致时报错；未传此参数时可采用地址中的端口 |
| `--output DIR` | 输出目录，默认 `dist/server` |
| `--resources-dir DIR` | 本地资源库，默认仓库 `resources/`；缺失文件自动下载到此处 |
| `--catalog FILE` | 指定资源清单 |
| `--runtime-base-url URL` | 运行文件镜像目录，须包含与锁一致的 `team-dev-env-runtimes.zip`；不改变摘要要求 |

`start` 固定使用 HTTP，不采用 `dev-kit` Shell 配置里的默认本机地址。多网卡时可用 `--server` 明确指定；非交互运行若有多个候选、无候选或检测失败，也须传入该参数。下载地址会固化进入启动入口和 `.support/config/team.sh`，成员无需填写；IP 变化后重新 `start`，并让成员重新下载启动包。可从 `server/config.example.json` 建立目录和端口配置，完整优先级见[服务启动指南](service-startup.md#配置与优先级)。

单独补齐运行文件使用 `python3 server/manage.py prepare-runtimes`；加 `--offline` 只校验本地、不联网或写入。镜像可由 `start`、`preview`、`prepare-runtimes` 的 `--runtime-base-url` 或 JSON 的 `runtime_base_url` 指定，默认使用锁定的 GitHub Release。镜像 URL 指向 ZIP 所在目录；归档及七个成员的 SHA-256、大小和源码匹配关系仍必须通过校验。

高级默认值由维护者在 [dev-kit/.support/config/env.sh](../dev-kit/.support/config/env.sh) 中管理，例如 JDK 安装目录、包路径和版本。需要改动团队配置时，修改后重新打包并发布，成员菜单会自动使用这些安装默认值。`MYSQL_IMAGE`、端口、数据库名等设置仅供维护者的可选 MySQL 命令行服务使用，配置文件不保存 MySQL 密码；不要把维护者机器上的绝对目录、凭据或测试数据写入分发配置。

输出文件如下：

```text
dist/server/
├── start.zip                         # 安装、卸载两个可执行的双击入口
├── start.command                     # 安装下载入口，供维护者 CLI / 调试
├── uninstall.command                 # 卸载下载入口，供维护者 CLI / 调试
├── release.json                      # 实际发布版本、源码摘要与六个发布文件的摘要/大小
├── dev-env/
│   ├── team-dev-env.tar.gz            # 启动入口自动下载的完整工具
│   └── team-dev-env.tar.gz.sha256     # 工具包校验值
├── team-dev-env.zip                   # 完整工具备用下载
└── resources/                        # start 自动导出的独立资源目录
```

成员工具发布版本为 `go-tui-<实际 dev-env/team-dev-env.tar.gz 的 SHA-256 前 12 位>`。`release.json` 的 `interface` 为 `go-tui`，记录发布时间、两个运行文件源码摘要，以及上方六个发布文件各自的大小和 SHA-256。它与维护者运行文件 ZIP 的 `runtimes-…` 版本用途不同：前者标识当前托管的完整成员工具，后者锁定预构建运行文件。将就绪输出的 `start.zip?v=go-tui-…` 链接发给成员，可区分本次发布与旧下载链接。

启动 ZIP 只含两个轻量下载入口；JDK、Gradle、DMG 和插件 ZIP 都在独立资源目录，不进入启动 ZIP 或完整工具 ZIP。本地完整资源库应保留供重复启动时复用、校验和生成成员清单。源码中的成员工具位于 `dev-kit/`，打包后解压为：

```text
team-dev-env/
├── 开始配置.command
├── 卸载环境.command
├── 使用说明.txt
└── .support/                         # Finder 默认隐藏，无需成员操作
    ├── install_env.sh
    ├── menu.sh
    ├── cleanup/                      # 自带运行时的卸载工具、清单和许可
    ├── tui/                          # Go双架构界面、清单和许可
    ├── config/
    │   ├── env.sh
    │   ├── team.sh                   # 打包时生成
    │   └── resources.tsv             # 打包时生成的成员资源与摘要清单
    └── scripts/
```

`docs/`、`tests/`、`tools/` 和根目录 `install_env.sh` 不分发给成员。ZIP 会保存入口执行权限；请使用能保留这些权限的解压方式。

## 高级：分步准备与独立服务器

准备运行文件、安装资源、打包和托管分开执行时，使用下面的流程。将示例地址改为成员最终访问的地址；Windows 将 `python3` 换成 `py -3`：

```bash
python3 server/manage.py prepare-runtimes
python3 server/manage.py prepare
python3 server/manage.py prepare --verify
python3 server/manage.py package --server "192.168.1.20:8080" --scheme http --with-resources --output dist/server
python3 server/manage.py serve --directory dist/server --bind 0.0.0.0 --port 8080
```

`package` 只校验本地运行文件与安装资源并打包，不联网、不启动服务。`serve` 启动前验证 `release.json` 和六个发布文件的摘要及大小，拒绝缺少新版清单的旧包或损坏包；通过后只读托管，不改写包。完整有效的历史发布目录也可托管，显示的是该目录的实际版本，不表示已同步最新源码。原生入口可显式传入这些子命令。运行文件由维护者预先构建并发布后，Windows 和 macOS 服务器均可自动获取并生成完整 ZIP、TAR 和启动包。Windows 尚未实机验收。启停、后台运行与下载检查见[服务启动指南](service-startup.md)。

本机测试可运行 `python3 server/manage.py preview --port 8081`，Windows 改用 `py -3`；原 Mac 命令 `bash tools/preview.sh --port 8081` 保持兼容。预览默认 `127.0.0.1:8081`，拿到端口后先补齐运行文件，再校验已有安装资源并使用本机地址重新打包；安装资源缺失时先运行 `prepare`。端口占用时先报错，不改发布物或关闭原服务，原地址可能仍是旧包。正式分发前重新 `start`，或用真实内网地址重新 `package`。

**网站根目录必须指向 `dist/server`（或实际打包输出目录），不是仓库根目录。** 例如请求 `/dev-env/team-dev-env.tar.gz` 应映射到 `dist/server/dev-env/team-dev-env.tar.gz`。文件存在于磁盘并不代表 HTTP 服务已经托管它；其他程序占用同一端口时，也可能返回 404。

在另一台服务器托管时，完成带资源打包后，把输出目录里的文件上传至该服务器根目录，保留相对路径。最终结构为：

```text
服务器根目录/
├── start.zip
├── start.command
├── uninstall.command
├── release.json
├── team-dev-env.zip
├── dev-env/
│   ├── team-dev-env.tar.gz
│   └── team-dev-env.tar.gz.sha256
└── resources/
    ├── runtime/
    │   ├── jdk/
    │   │   ├── jdk8-macos-arm64.tar.gz
    │   │   └── jdk8-macos-x64.tar.gz
    │   └── gradle/
    │       ├── gradle-4.5.1-bin.zip
    │       ├── gradle-4.5.1-bin.zip.sha256
    │       ├── gradle-6.8-bin.zip
    │       └── gradle-6.8-bin.zip.sha256
    ├── software/
    │   ├── idea/                    # 两种架构的 IDEA DMG
    │   └── dbeaver/                 # 两种架构的 DBeaver DMG
    └── plugins/idea/                # 六个原始插件 ZIP
```

每个安装包的同名 `.sha256` 随资源保留。JDK URL 以 `/resources/runtime/jdk/` 开头，Gradle URL 为 `/resources/runtime/gradle/gradle-4.5.1-bin.zip` 或 `/resources/runtime/gradle/gradle-6.8-bin.zip`。从旧目录升级时应重新发布工具和资源，使配置与这些路径一致；具体约定见[运行环境指南](environment/runtime.md)。以后只更新工具时保留服务器上的 `resources/`，不必重复上传大包。

高级流程中，`package --with-resources` 把资源放入输出目录。只更新工具时可省略 `--with-resources`，保留输出目录中已有资源；本地完整资源库仍须保留供打包校验。`package` 只创建本地文件，随后可交给 `serve` 或团队现有静态服务器托管。

发送链接前请完成以下检查：

- 核对就绪输出和 `/release.json` 的 `go-tui-…` 版本属于本次发布，不能只看 `git pull` 成功或旧端口仍能访问。
- 在另一台成员电脑能访问的机器上，下载 `start.zip` 并确认 URL 使用真实内网地址。
- 解压后确认入口可执行，双击检查首次打开提示，并确认能下载工具、通过校验及进入菜单。
- 在团队使用的 macOS 与浏览器组合上分别确认首开行为；Apple Silicon 和 Intel 使用各自的真实 JDK 包验证。
- 用菜单 `1` 验证全部环境安装配置，确认不选择项目、不执行构建；另用下方维护者命令指定团队测试项目完成真实 `build` 验证。
- 用维护者的 `download-tools.sh` 下载一个适配本机的软件和插件，确认能打开安装包、在 IDEA 中从磁盘安装插件。
- 分别用 `3.1` / `3.2` 验证两版 Gradle 独立安装，确认当前 `GRADLE_HOME` 切换且已配置的版本别名保留；子菜单 `0` 返回、空行不安装。
- 用菜单 `4` 验证 IDEA 安装到当前用户的 `~/Applications/IntelliJ IDEA CE.app`，并确认已有完整同版应用可复用。
- 用菜单 `5` 验证全部六个插件安装结果，打开本次历史目录或运行 `history.sh` 查看失败阶段及验证结果。
- 保留完整工具 ZIP 的备用下载链接。

完成这些操作后，再发送就绪输出中形如 `http://实际内网地址:端口/start.zip?v=go-tui-版本摘要` 的启动包链接。需要 HTTPS 时使用高级流程，由现有 HTTPS 静态服务器或反向代理提供证书，再用最终地址及 `package --scheme https` 打包；`start` 不配置 TLS。

已有用户须重新下载一次新版 `start.zip` 才能获得卸载入口。两个启动器每次运行都会下载最新发布的完整包并校验，不缓存旧工具；已解压的完整工具 ZIP 是快照，更新需重新下载。

更新工具时应一起替换 `release.json`、启动包、安装/卸载启动脚本、完整工具包及其校验文件，避免成员下载到不同版本的文件；更换服务器地址后重新 `start`（高级流程重新打包），并让成员下载新的启动包。

资源准备没有生成业务依赖缓存、JDBC 驱动缓存或 MySQL 镜像。完全断网使用前，还需项目维护者补齐这些内容并验证实际构建与数据库连接。

## 首次打开与故障处理

浏览器直接下载 `start.command` 时可能不保留执行权限，因此不把它作为成员的默认入口。优先下载 `start.zip`；若启动下载失败，可改用完整工具 ZIP。

ZIP 能保留执行权限，但不会绕过 macOS 的来源检查。首次打开网络下载的入口时，系统可能要求确认来源。仅在确认文件来自团队可信服务器后，按照系统提示打开；如出现相应选项，可在「系统设置 → 隐私与安全性」中允许这一个文件。受公司设备策略管理的电脑可能需要 IT 协助。

[Apple 的安全打开说明](https://support.apple.com/en-us/102445)介绍了通用安全提示和允许打开的方式；它不是对本工具 `.command` 文件的兼容性验证，具体提示须以当前 macOS 的实际行为为准。本工具不会自动删除隔离标记，也不要求全局关闭安全检查。

常见情况：

| 情况 | 处理 |
| --- | --- |
| 双击没有执行权限或文件被当成文本打开 | 重新下载并解压 `start.zip`；仍失败请联系维护者检查解压权限和文件后缀 |
| 无法下载或连接拒绝 | 确认内网连接，维护者检查服务器地址、端口、文件路径；不要让成员改成 `127.0.0.1` |
| HTTP 404 | 查看启动器显示的完整下载地址；确认端口属于本工具服务，网站根目录为打包输出目录，且 `dev-env` 内的 TAR 与校验文件已一并发布 |
| 完整工具校验失败 | 停止使用这次下载；维护者确认包与校验文件来自同一次打包，再重新下载 |
| 代码已拉取但界面仍旧 | 检查本次 `start` 是否完成，核对 `/release.json` 实际版本；端口占用退出不会重新发布 |
| `serve` 拒绝发布目录 | 用 `start` 或 `package` 重新生成完整的六个发布文件和 `release.json`，不要手改摘要 |
| 安装时下载失败或提示资源缺失 | 维护者重新运行 `start`，或确认高级 `package` 使用了 `--with-resources`；保留 `resources/` 下的目录、文件和校验文件 |
| 维护者项目验证提示缺少构建文件 | 用 `--project` 指定包含 `build.gradle` 或 `build.gradle.kts` 的实际业务项目；独立 Gradle 安装不要求 Wrapper |
| 菜单 `3` 无法完成验证 | 检查 JDK、资源地址、SHA-256、完整环境变量和阶段日志；见 [Gradle 指南](environment/gradle.md) |
| 菜单 `4` 提示 IDEA 目标已存在但不可复用 | 保留现有应用；若是旧 2024 版，先按卸载引导核对并确认删除，再安装 2025；其他冲突请维护者检查后重试 |
| 配置后当前终端仍显示旧 Java | 重新打开终端；IDEA 另行设置 Project SDK 和 Gradle JVM |
| 维护者命令行启动本地 MySQL 失败 | 确认 Docker 已启动、端口未占用，并使用团队确认的 MySQL 镜像版本 |
| 修复后仍显示失败 | 打开输出的历史目录查看失败阶段；组件安装完成不代表复验或项目构建通过，不要忽略失败后继续宣称整体成功 |

菜单日志位于 `$HOME/Library/Logs/team-java-env`，修复历史默认位于其 `history/` 子目录，可直接打开目录或通过维护者的 `history.sh` 查看。记录包含修复前后扫描、阶段结果和日志；菜单操作明确记录未执行项目构建。菜单启动预检不创建修复历史。发送日志前确认没有密码、令牌等敏感内容；尚未进入菜单就下载失败时，保留窗口提示。

## 维护者命令行入口

Mac 维护者可在仓库根目录直接调用修复流程：

```bash
bash dev-kit/.support/scripts/repair-env.sh --scope all --project "/absolute/path/to/java-project" --dry-run
bash dev-kit/.support/scripts/repair-env.sh --scope all --project "/absolute/path/to/java-project"
bash dev-kit/.support/scripts/repair-env.sh --scope gradle --gradle-version 6.8
bash dev-kit/.support/scripts/check-env.sh --project "/absolute/path/to/java-project"
bash dev-kit/.support/scripts/history.sh
```

完整工具解压后使用其中的同一脚本：

```bash
bash "team-dev-env/.support/scripts/repair-env.sh" --scope all --project "/absolute/path/to/java-project"

# 使用打包后的资源清单，仅下载软件或插件
bash "team-dev-env/.support/scripts/download-tools.sh" --list
bash "team-dev-env/.support/scripts/download-tools.sh" --id lombok

# 可选 MySQL 服务预览；实际启动要求 Docker 和 MYSQL_ROOT_PASSWORD
bash "team-dev-env/.support/scripts/services/mysql.sh" up --dry-run
```

`--dry-run` 仅预览，不安装、不构建、不创建历史目录。省略 `--project` 时仍可修复环境，但会明确记录“未执行项目构建”。这些是 Mac 客户端操作；Windows 服务端使用前述 Python 命令管理分发文件。

## npm / npx 入口

`npm-cli/` 生成的临时包只封装同一个下载模板，不携带服务器私有地址；由 `--server` 指定内网服务。它适合已有 Node/npm 的成员，首次无 Node 的成员仍使用 `start.zip`。本地验证、正式定名与发布步骤见[前端环境指南](environment/frontend.md#npm-打包与-npx-使用)。新增前端脚本随完整工具包下发；修改源码后仍须重新打包服务器资源和工具。
