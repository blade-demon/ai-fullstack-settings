# 内网分发指南

维护者可在 Windows 或 macOS 上用 Python 3.8+ 准备资源、打包和运行下载服务，服务端不依赖 Bash。小组成员仍使用 macOS 中文安装入口，无需配置服务器地址，也无需安装 Python、Homebrew 或 Git。Windows 服务端不代表提供了 Windows 安装客户端。

首次部署前，先在实际运行脚本的电脑或服务器上完成[Python 3 安装与验证](service-startup.md#部署前安装-python-3)。服务端只使用标准库，无需安装第三方 Python 包。

**先启动下载服务，再运行成员启动包。** 本机与内网服务器的完整启动命令、停止/重启和端口处理见[服务启动指南](service-startup.md)。打包输出的链接只有在服务启动且根目录配置正确后才能访问。

## 成员操作流程

1. 连接团队内网，打开维护者提供的 `start.zip` 下载链接。
2. 解压启动包，双击其中的「开始配置.command」。入口自动下载完整工具、校验 SHA-256、解压；菜单打开时先自动预检现有 JDK 8 和 Gradle 状态。
3. 已有业务项目时，先用菜单 `3` 选择或切换项目；根目录应包含 `build.gradle` 或 `build.gradle.kts`。取消选择保留之前的项目，初次未选则保持无项目。
4. 选择菜单 `1` 一键检查并修复环境：补齐 JDK、独立 Gradle、完整环境变量、IDEA 和插件，再复验。已有所选项目时还会执行真实 `build`（含测试），构建通过才报告整体成功；没有项目时只报告环境验证结果和“未执行项目构建”。
5. 也可用菜单 `2`、`7`、`8`、`9` 分别处理 JDK、Gradle、IDEA 和全部 IDEA 插件。IDEA 位于 `~/Applications/IntelliJ IDEA CE.app`，其项目设置见 [IDE 指南](environment/ide.md)。
6. 菜单 `6` 继续提供只下载入口，DBeaver 下载后手动安装；插件也可在 IDEA 中通过 `Install Plugin from Disk` 手动安装原始 ZIP。菜单 `10` 查看修复历史与阶段结果。

菜单提供以下操作：

| 选项 | 操作 |
| --- | --- |
| `1` | 一键检查、修复并复验环境；使用当前选择的项目，有项目时必须通过真实构建 |
| `2` | 单独修复 JDK 8 和完整 Java 环境变量 |
| `3` | 可选择或切换项目，刷新只读环境检查并保存日志；取消则检查此前项目或仅检查本机 |
| `4` | 启动本地 MySQL，按提示输入本地开发密码；需要 Docker |
| `5` | 停止本地 MySQL，保留数据卷 |
| `6` | 下载开发软件 / IDEA 插件；按本机架构展示资源，只下载、不安装 |
| `7` | 单独安装 Gradle 4.5.1 和完整变量；可选项目，选定后执行真实构建 |
| `8` | 安装 IDEA 到个人应用目录；按架构下载、校验并复制到 `~/Applications/IntelliJ IDEA CE.app` |
| `9` | 安装并验证清单中的全部 IDEA 插件 |
| `10` | 查看修复历史、阶段结果和日志位置 |
| `0` | 退出 |

自动预检不下载或安装；菜单 `3` 可刷新检查并留存结果。扫描结果用于判断待修复项，不代替实际 SDK、完整环境变量、IDEA、插件和项目构建验证。仅有安装包或 Wrapper 缓存，不能代表独立 Gradle 和项目已经就绪。

修复流程先扫描，复用通过验证的已有组件，再补齐缺失内容并检查修复结果。JDK 与 Gradle 安装在成员用户目录，完整变量包括 `JAVA_HOME`、`JAVA_8_HOME`、`JRE_HOME`、`GRADLE_HOME`、`GRADLE_4_5_1_HOME`、`GRADLE_USER_HOME` 及对应 `PATH`。发生冲突或验证失败时保留原文件并记录失败阶段，不把“安装步骤结束”当作最终成功。

已有 IDEA 项目配置时，有项目的修复会在构建前统一 JDK 8 的 SDK 登记与项目引用名称，默认 `azul-1.8`，可由维护者通过 `IDEA_JDK_NAME` 配置。执行前须退出 IDEA；同目录的重复 SDK 名称会合并。尚未导入的项目仍提示待配置，之后完成导入并运行名称同步，见 [IDE 指南](environment/ide.md#统一-jdk-8-登记与项目引用)。

菜单 `6` 只下载，把文件保存到 `~/Downloads/team-java-env/` 的对应子目录。菜单 `8` 校验 IDEA DMG 后只读挂载，将应用复制到当前用户的 `~/Applications`，无需 `sudo`，不修改系统 `/Applications`，也不自动启动 IDEA。同版本、同 build 且完整的现有应用会复用；其他已有目标保留并报错，不覆盖。手动安装和两个应用目录的区别见 [IDE 指南](environment/ide.md)。

工具不下载业务项目，Docker 本次仅登记官方入口，未纳入下载清单。完整工具包 `team-dev-env.zip` 是备用入口：解压后双击 `team-dev-env/开始配置.command`，同样进入菜单；隐藏的 `.support` 必须与入口保持在一起。

菜单 `7` 安装独立 Gradle，不要求项目带有 Wrapper。选择目录时取消会保留之前的项目；仍未选择项目时，只安装和验证 Gradle 及变量。已有项目时，实际执行目标 Gradle 的 `build`（含测试），失败即保留失败结果；需要的企业依赖仓库、网络和权限由团队提供。详细说明见[Gradle 安装指南](environment/gradle.md)。

## 维护者一键准备与启动

在实际运行下载服务的机器上，进入项目根目录执行。以下用 macOS 的 `python3`；Windows 将其替换为 `py -3` 或已确认版本的 `python`：

```bash
python3 server/manage.py start
```

也可双击 Windows 的 `server/start-server.cmd` 或 macOS 的 `server/start-server.command`；无参数时均执行 `start`。它自动检测本机活动 IPv4 地址，多个候选时在终端选择序号；先占用默认 `8080` 端口，再校验资源、补缺下载、带资源打包并显示真实 HTTP 下载链接。服务监听 `0.0.0.0`，窗口需要保持运行。自动检测不保证成员网段、防火墙或 VPN 已允许访问，分发前仍须从成员电脑验证。

资源下载默认保存到仓库 `resources/`，清单包含 JDK 8、Gradle 4.5.1、IDEA 社区版、DBeaver 和六个免费 IDEA 插件；全部约 2.53 GB。重复执行时，已有且校验通过的资源会复用；损坏文件保留并报错，不自动覆盖。来源、版本、分组筛选和校验方式见[资源准备指南](resources/README.md)。

| 参数 | 含义 |
| --- | --- |
| `--server HOST[:PORT]` | 覆盖自动选址，指定成员可访问的主机或 IP，不含协议或路径 |
| `--port PORT` | 默认 `8080`；与显式 `--server` 中的端口不一致时报错；未传此参数时可采用地址中的端口 |
| `--output DIR` | 输出目录，默认 `dist/server` |
| `--resources-dir DIR` | 本地资源库，默认仓库 `resources/`；缺失文件自动下载到此处 |
| `--catalog FILE` | 指定资源清单 |

`start` 固定使用 HTTP，不采用 `dev-kit` Shell 配置里的默认本机地址。多网卡时可用 `--server` 明确指定；非交互运行若有多个候选、无候选或检测失败，也须传入该参数。下载地址会固化进入启动入口和 `.support/config/team.sh`，成员无需填写；IP 变化后重新 `start`，并让成员重新下载启动包。可从 `server/config.example.json` 建立目录和端口配置，完整优先级见[服务启动指南](service-startup.md#配置与优先级)。

高级默认值由维护者在 [dev-kit/.support/config/env.sh](../dev-kit/.support/config/env.sh) 中管理，例如 JDK 安装目录、包路径和版本，以及 `MYSQL_IMAGE`、端口、数据库名等 MySQL 设置。需要改动团队配置时，修改后重新打包并发布，成员菜单会自动使用这些默认值。配置文件不保存 MySQL 密码；不要把维护者机器上的绝对目录、凭据或测试数据写入分发配置。

输出文件如下：

```text
dist/server/
├── start.zip                         # 推荐下载；含可执行的「开始配置.command」
├── start.command                     # 原始启动脚本，供维护者 CLI / 调试
├── dev-env/
│   ├── team-dev-env.tar.gz            # 启动入口自动下载的完整工具
│   └── team-dev-env.tar.gz.sha256     # 工具包校验值
├── team-dev-env.zip                   # 完整工具备用下载
└── resources/                        # start 自动导出的独立资源目录
```

启动 ZIP 只含启动入口；JDK、Gradle、DMG 和插件 ZIP 都在独立资源目录，不进入启动 ZIP 或完整工具 ZIP。本地完整资源库应保留供重复启动时复用、校验和生成成员清单。源码中的成员工具位于 `dev-kit/`，打包后解压为：

```text
team-dev-env/
├── 开始配置.command
├── 使用说明.txt
└── .support/                         # Finder 默认隐藏，无需成员操作
    ├── install_env.sh
    ├── menu.sh
    ├── config/
    │   ├── env.sh
    │   ├── team.sh                   # 打包时生成
    │   └── resources.tsv             # 打包时生成的成员资源与摘要清单
    └── scripts/
```

`docs/`、`tests/`、`tools/` 和根目录 `install_env.sh` 不分发给成员。ZIP 会保存入口执行权限；请使用能保留这些权限的解压方式。

## 高级：分步准备与独立服务器

准备资源、打包和托管分开执行时，使用下面的四步流程。将示例地址改为成员最终访问的地址；Windows 将 `python3` 换成 `py -3`：

```bash
python3 server/manage.py prepare
python3 server/manage.py prepare --verify
python3 server/manage.py package --server "192.168.1.20:8080" --scheme http --with-resources --output dist/server
python3 server/manage.py serve --directory dist/server --bind 0.0.0.0 --port 8080
```

`package` 不下载缺失资源或启动服务；`serve` 只读托管已经打包的目录，不改写包。原生入口也可显式传入这些子命令。两系统无需先在 Mac 上制作发布包；Windows 尚未实机验收。启停、后台运行与下载检查见[服务启动指南](service-startup.md)。

本机测试可运行 `python3 server/manage.py preview --port 8081`，Windows 改用 `py -3`；原 Mac 命令 `bash tools/preview.sh --port 8081` 保持兼容。预览默认 `127.0.0.1:8081`，会使用本机地址重新打包；端口占用时先报错，不改发布物或关闭原服务。正式分发前重新 `start`，或用真实内网地址重新 `package`。

**网站根目录必须指向 `dist/server`（或实际打包输出目录），不是仓库根目录。** 例如请求 `/dev-env/team-dev-env.tar.gz` 应映射到 `dist/server/dev-env/team-dev-env.tar.gz`。文件存在于磁盘并不代表 HTTP 服务已经托管它；其他程序占用同一端口时，也可能返回 404。

在另一台服务器托管时，完成带资源打包后，把输出目录里的文件上传至该服务器根目录，保留相对路径。最终结构为：

```text
服务器根目录/
├── start.zip
├── start.command
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
    │       └── gradle-4.5.1-bin.zip.sha256
    ├── software/
    │   ├── idea/                    # 两种架构的 IDEA DMG
    │   └── dbeaver/                 # 两种架构的 DBeaver DMG
    └── plugins/idea/                # 六个原始插件 ZIP
```

每个安装包的同名 `.sha256` 随资源保留。JDK URL 以 `/resources/runtime/jdk/` 开头，Gradle URL 为 `/resources/runtime/gradle/gradle-4.5.1-bin.zip`。从旧目录升级时应重新发布工具和资源，使配置与这些路径一致；具体约定见[运行环境指南](environment/runtime.md)。以后只更新工具时保留服务器上的 `resources/`，不必重复上传大包。

高级流程中，`package --with-resources` 把资源放入输出目录。只更新工具时可省略 `--with-resources`，保留输出目录中已有资源；本地完整资源库仍须保留供打包校验。`package` 只创建本地文件，随后可交给 `serve` 或团队现有静态服务器托管。

发送链接前请完成以下检查：

- 在另一台成员电脑能访问的机器上，下载 `start.zip` 并确认 URL 使用真实内网地址。
- 解压后确认入口可执行，双击检查首次打开提示，并确认能下载工具、通过校验及进入菜单。
- 在团队使用的 macOS 与浏览器组合上分别确认首开行为；Apple Silicon 和 Intel 使用各自的真实 JDK 包验证。
- 用团队测试项目执行一键修复，确认独立 Gradle 4.5.1、完整变量与真实 `build` 均通过；只显示版本不能作为最终项目验收。
- 用菜单 `6` 下载一个适配本机的软件和插件，确认能打开安装包、在 IDEA 中从磁盘安装插件。
- 用菜单 `8` 验证 IDEA 安装到当前用户的 `~/Applications/IntelliJ IDEA CE.app`，并确认已有完整同版应用可复用。
- 用菜单 `9` 验证插件安装结果，用菜单 `10` 查看本次修复历史、失败阶段或构建结果。
- 保留完整工具 ZIP 的备用下载链接。

完成这些操作后，再发送形如 `http://实际内网地址:端口/start.zip` 的启动包链接。需要 HTTPS 时使用高级流程，由现有 HTTPS 静态服务器或反向代理提供证书，再用最终地址及 `package --scheme https` 打包；`start` 不配置 TLS。

更新工具时应一起替换启动包、启动脚本、完整工具包及其校验文件，避免成员下载到不同版本的文件；更换服务器地址后重新 `start`（高级流程重新打包），并让成员下载新的启动包。

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
| 菜单 `6` 下载失败或提示资源缺失 | 维护者重新运行 `start`，或确认高级 `package` 使用了 `--with-resources`；保留 `resources/` 下的目录、文件和校验文件 |
| 项目缺少构建文件 | 选择包含 `build.gradle` 或 `build.gradle.kts` 的实际业务项目；独立 Gradle 安装不要求 Wrapper |
| 菜单 `7` 无法完成验证 | 检查 JDK、资源地址、SHA-256、完整环境变量，以及项目真实构建日志；见 [Gradle 指南](environment/gradle.md) |
| 菜单 `8` 提示 IDEA 目标已存在但不可复用 | 保留现有应用；检查是否为其他版本或不完整文件，请维护者协助处理后再重试 |
| 配置后当前终端仍显示旧 Java | 重新打开终端；IDEA 另行设置 Project SDK 和 Gradle JVM |
| 本地 MySQL 启动失败 | 确认 Docker 已启动、端口未占用，并使用团队确认的 MySQL 镜像版本 |
| 修复后仍显示失败 | 用菜单 `10` 查看失败阶段；组件安装完成不代表复验或项目构建通过，不要忽略失败后继续宣称整体成功 |

菜单日志位于 `$HOME/Library/Logs/team-java-env`，修复历史默认位于其 `history/` 子目录，可通过菜单 `10` 查看。记录包含修复前后扫描、阶段结果和日志；未选项目时会明确记录未执行项目构建。菜单启动预检不创建修复历史。发送日志前确认没有密码、令牌等敏感内容；尚未进入菜单就下载失败时，保留窗口提示。

## 维护者命令行入口

Mac 维护者可在仓库根目录直接调用修复流程：

```bash
bash dev-kit/.support/scripts/repair-env.sh --scope all --project "/absolute/path/to/java-project" --dry-run
bash dev-kit/.support/scripts/repair-env.sh --scope all --project "/absolute/path/to/java-project"
```

完整工具解压后使用其中的同一脚本：

```bash
bash "team-dev-env/.support/scripts/repair-env.sh" --scope all --project "/absolute/path/to/java-project"
```

`--dry-run` 仅预览，不安装、不构建、不创建历史目录。省略 `--project` 时仍可修复环境，但会明确记录“未执行项目构建”。这些是 Mac 客户端操作；Windows 服务端使用前述 Python 命令管理分发文件。
