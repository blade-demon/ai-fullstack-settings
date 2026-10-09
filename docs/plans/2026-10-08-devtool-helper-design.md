# devtool-helper.sh 统一交付入口设计

日期：2026-10-08

状态：已实施，2026-10-09 完成本地隔离验收。统一 install/uninstall 入口与 Go TUI，支持六类组件选择、进度和版本切换；成员发布仅生成一个 Shell 入口、一个 TAR 工具包和一份发布清单。实施清单见[实施计划](2026-10-08-devtool-helper-implementation.md)，实际验证与远端发布限制见[验证记录](../verification.md#2026-10-09统一-helper-交付与六组件管理)。

## 设计结论

将面向新成员的交付文件统一为 `devtool-helper.sh` 是合理的。成员下载一个文件，通过 `bash devtool-helper.sh` 打开现有终端界面，也可以用 `install`、`uninstall` 直接进入配置或卸载流程。服务器地址仍由维护者在打包时写入，成员无需安装 Python、Node、Go 或 Homebrew。

脚本负责选择入口、下载工具包、校验和启动。安装层复用已有组件脚本并增加统一任务调度，Go TUI 增加选择和进度展示，卸载运行时扩展为按组件生成清理计划。单文件交付指成员只需获取一个启动文件；SDK、界面程序和卸载工具仍从团队服务器下载，并非把全部工具内嵌为离线脚本。

成员工具只有一个压缩格式 `team-dev-env.tar.gz`，删除备用 `team-dev-env.zip`。工具包摘要和大小统一记录在 `release.json`，不生成单独的工具包 `.sha256` 文件。常规打包只生成三个发布文件；运行文件发布、npm 包和预览目录各自按明确用途生成，不能顺带批量产生副本。

默认无参数打开 Go TUI 首页，提供“安装与配置”“卸载工具”“一键安装配置全部”。安装和卸载页均按 JDK、Gradle、nvm、IDEA、iTerm2、Oh My Zsh 六类选择，不再增加 Shell 选择菜单。明确执行 `uninstall` 时直接打开卸载选择页，继续避免执行已安装 SDK 的运行探测。

交互菜单统一使用 Go TUI。删除原 Bash 数字菜单、`--plain` 模式及界面失败时退回文本菜单的说明。参数化安装命令、只读预演与日志输出仍保留；TUI 调用卸载器时选择删除范围、核对计划及输入 `DELETE` 的安全确认继续保留，这些确认不属于被删除的备用菜单。

新交付以终端运行方式为准，不承诺 `.sh` 可以双击，也不把修改后缀描述为免除 macOS 安全检查。现有 `.command` 已是 Bash 脚本且有执行权限；从终端运行和从 Finder 双击的检查路径不同。若将来要求普通用户直接双击，应另行设计签名、公证的应用或安装包。[Apple 技术说明](https://developer.apple.com/forums/thread/706379)、[Apple 安全提示说明](https://support.apple.com/zh-cn/102445)。

## 实施前结构与约束

| 位置 | 当前职责 | 对本次设计的影响 |
| --- | --- | --- |
| `tools/start.command.in` | 生成轻量下载器，通过 `ENTRY_NAME` 选择安装或卸载入口 | 合并公共入口时，需要显式解析子命令，不能靠保存文件名决定行为 |
| `server/manage.py` | 当前生成双下载器、两个 ZIP、TAR、摘要和发布信息 | 收敛为三个文件，按需映射/复制资源，集中处理旧产物退场 |
| `server/publication.py` | 当前以 schema 1 校验六项文件 | 更新为 schema 2，统一记录入口及工具包摘要和大小，删除重复摘要产物 |
| `dev-kit/开始配置.command`、`dev-kit/卸载环境.command` | 两份包内调度包装器 | 合并到一个 `run-tool.sh`，不再进入 TAR |
| `dev-kit/.support/menu.sh` | 原 Bash 数字菜单 | 删除源码及打包白名单条目 |
| `tui/actions.go`、`tui/ui.go`、`tui/runner.go` | 现有菜单按 Java/前端组织，只有阶段状态事件 | 增加六类组件选择、统一任务计划、总任务条和当前阶段条 |
| `tools/uninstall_java_gradle.py` | 目前扫描 JDK/Gradle，并可选择 IDEA；尚无前端卸载 | 新增真正的组件过滤，以及 nvm、iTerm2、Oh My Zsh 清理与独立配置处理 |
| `npm-cli/` | 当前与分发器共用下载模板，另有独立 frontend 路由 | 删除 frontend 路由，统一 install/uninstall 与组件参数 |
| `dev-kit/.support/scripts/lib/managed-env.sh` | 保存两版 Gradle 路径，安装时覆盖活动版本 | 分离版本登记和默认激活，自动生成可长期使用的切换函数 |
| `dev-kit/.support/scripts/runtime/install-node.sh` | 已通过 nvm 验证版本、设置默认别名和生成加载区块 | 保留 nvm 作为唯一 Node 切换机制，补齐自动配置验证和安装后指引 |

成员客户端仍只支持 macOS，兼容系统自带 Bash 3.2。维护者仍可在 Windows 或 macOS 使用 Python 服务端；生成 `.sh` 不要求 Windows 服务器运行 Bash。

## 方案选择

| 方案 | 使用方式与影响 | 结论 |
| --- | --- | --- |
| 一个 Shell 入口扩展现有 TUI | 在现有终端界面中增加六组件选择及进度；复用下载和组件安装层 | 采用 |
| Shell 先显示安装和卸载菜单 | 选择后再下载；安装后又进入现有主菜单，增加一次选择及一套交互维护 | 本次不采用 |
| 将安装器、卸载器及界面全部合并到脚本 | 文件体积、更新和维护成本增加，无法直接复用已有运行文件 | 本次不采用 |

完整工具仅生成 TAR，包内安装/卸载共用一个 `dev-kit/.support/scripts/run-tool.sh`，通过固定 `install` 或 `uninstall` 参数分流。删除两份 `.command` 包装器及旧文本菜单，不将维护者使用说明打入临时执行包。TAR 内保留实际功能脚本、配置、运行文件、必要校验清单和第三方许可；成员可见入口统一为 helper。

## 组件选择与一键安装

### 安装和卸载页面

安装页与卸载页都展示六个固定组件。上下方向键移动，空格勾选；安装页左右方向键切换当前组件可选版本，Enter 直接开始安装已选项，不再跳转到单独的计划预览或确认页。空选择不会执行默认安装或删除。每项展示检测状态、明确的默认版本、目标目录和是否由本工具管理；依赖补入、默认版本切换等影响在当前页同步展示。

安装页按 Enter 后先做必要预检，通过即进入带进度条的执行页；预检失败则留在选择页显示原因，不开始安装，也不再要求一次额外确认。卸载页默认全部不选中，先静态识别文件和收据，不运行待卸载软件；其 Enter 进入删除清单与 `DELETE` 确认，避免与安装快捷执行混淆。

```text
安装与配置                       已选择 2 项

  [x] JDK          JDK 8                  待安装
  [x] Gradle       4.5.1                   待安装
  [ ] nvm          Node 14.21.3            未配置
  [ ] IDEA         应用与推荐插件           可复用
  [ ] iTerm2       终端应用                 待安装
  [ ] Oh My Zsh    框架与推荐插件           待安装

  空格 选择    ←/→ 切换版本    Enter 开始安装    Esc 返回
```

组件标识固定为 `jdk`、`gradle`、`nvm`、`idea`、`iterm2`、`oh-my-zsh`。界面名称和命令行标识分开，底层已有 `node`、`zsh` 名称通过明确映射复用，不直接作为新增公共标识。

| 组件 | 安装与配置范围 | 卸载选择与边界 |
| --- | --- | --- |
| JDK | 沿用当前 JDK 8 基线，安装并配置相关变量，验证可用性 | 按实例选择带有效来源标记的 JDK；不附带删除 Gradle 或 IDEA |
| Gradle | 4.5.1、6.8 可独立并存；自动配置版本登记、当前会话切换和新终端默认版本，并展示切换用法 | 按实例清理所选版本、登记和默认引用，保留其他版本及用户缓存 |
| nvm | 支持仅安装 nvm，或加 Node 10、14、18、22 单版/全部四版；自动配置 nvm 加载和默认别名，展示 nvm 切换用法 | 展示 nvm 与各 Node 版本的归属及影响；只处理可确认归属的对象，保留外部版本和用户内容 |
| IDEA | 安装应用及现有六个推荐插件；复用已有安装，已存在可用 JDK 时配置其 SDK 引用 | 选择具体 IDEA 应用；可选择保留用户配置、SDK 登记及插件，保留现有最终确认规则 |
| iTerm2 | 安装、验证应用及来源收据，不更改系统默认终端 | 仅删除与可信来源收据绑定的应用；默认保留偏好、历史和会话数据 |
| Oh My Zsh | 安装框架，配置 git、z、zsh-autosuggestions、zsh-syntax-highlighting；保留用户主题及登录 Shell | 分别识别受管框架和外部插件，只清理本工具的配置区块；不删除系统 zsh、Git 或 CLT |

nvm 已确认支持“可选 Node 版本，也可仅安装 nvm”。新安装版本集合调整为 Node 10、14、18、22；`all` 仅表示这四版，Node 16 不再列入新安装选择。每个主版本使用维护者核验后在资源清单锁定的补丁版本、下载地址和 SHA-256，运行时不从 `latest` 动态选择补丁版。

安装集合变化不会自动卸载已有 Node 16。`all` 和 `none` 保留仍指向它的有效默认别名；用户明确选择单版安装时，按当前页已展示的变更将默认切到所选版本。卸载发现不受新安装白名单限制，历史版本仍按来源和用户选择处理；只有选中对应实例并完成删除确认后才卸载。

IDEA 内部 JBR 不是独立 JDK 卸载候选；只安装 IDEA 不隐式安装 JDK。未选 JDK 且系统无可用 JDK 时，SDK 关联不列为 IDEA 必需任务，显示独立的未配置提示，应用和插件验证通过即可计为组件完成；若 SDK 关联已纳入本次执行范围却失败或因 JDK 失败而跳过，IDEA 标记待处理，不计为完整完成。

### 一键安装配置全部

首页的“一键安装配置全部”旁展示默认组件、版本及配置范围，选中后按 Enter 即预检并连续执行六组件，不另弹计划确认页，也不需要逐项再次启动。需要调整版本时进入安装选择页修改后按 Enter 执行。它包含全部六类工具，不再等同于旧 Java `--scope all`，也不等同于旧前端 `--component all`。

全量默认配置为 JDK 8、Gradle 4.5.1、nvm 加 Node 14.21.3、IDEA 及六个推荐插件、iTerm2、Oh My Zsh 及四个推荐插件。安装选择页可改选 Gradle 6.8/两版或调整 Node 范围，不存在已勾选却没有有效版本的“待选择版本”默认状态。安装页与未指定 --node-version 时也默认选择并安装14.21.3。其他单版/none/all 仍可选；显式 all 才安装全部四版，首次或旧 default 失效时回退到14，已有有效默认版本保持不变；单一 Node 版本（包括默认单14）安装时将其设为默认，并在当前页展示变更；仅安装 nvm 时不下载 Node，也不创建或修改 Node 默认别名。

选择两版 Gradle 时保留已有有效默认版本；没有有效默认时使用 4.5.1。单独安装某一版时将其设为默认，并在安装选择页提前展示该配置变化。安装队列先确定最终默认值，不能让最后安装的版本隐式成为默认；已有其他版本目录继续保留。

执行前生成内部固定计划，检查资源、目标目录冲突和已有前提条件；内部计划用于准确执行和进度计数，不作为额外用户步骤。Gradle 需要的 JDK 只计入一次，并在选择页显示为依赖项；单独选择 Gradle 时也能看见将补齐或验证的 JDK。Oh My Zsh 的 Git 前提继续使用原检查，不自动接受系统安装或许可。

Node 10、14 使用官方 macOS x64 包；Apple Silicon 上先检查 Rosetta，下载和校验后、安装发布前验证所选二进制能实际运行，不回退源码编译或自动安装 Rosetta。Node 18、22 按机器架构选取 arm64 或 x64 包；具体补丁版的系统要求、资源摘要和实际运行验证纳入发布验收。架构依据为 [Node 10 官方归档](https://nodejs.org/en/download/archive/v10.24.1)、[nvm 官方 macOS 说明](https://github.com/nvm-sh/nvm#macos-troubleshooting)及 [Node 22 官方发行说明](https://nodejs.org/en/blog/release/v22.0.0)。

执行顺序固定为 JDK → Gradle → nvm/Node → iTerm2 → Oh My Zsh → IDEA/插件。只选择部分组件时，所选组件及补入的依赖仍按这个相对顺序执行，不按勾选先后改变顺序。SDK 版本及插件属于对应组件内的子任务，六类全选时总组件数仍为六。预检发现依赖或冲突时，TTY 留在或返回安装选择页，保留选择并列明受影响项；非 TTY 输出原因并返回非零，不等待输入、不执行任何组件。用户调整选择或满足前提后再按 Enter，重新预检并执行，不静默省略组件并声称“全部完成”。

正式执行中，组件失败后标记失败；依赖它的任务标为“未执行：依赖失败”，其他独立组件继续运行。用户取消则停止剩余任务并等待当前进程组退出。只有所有计划内组件均完成验证才报告全部成功；失败、取消及需要用户处理的保留项单独呈现，不自动回滚已成功安装的软件。

卸载也支持单选和多选，但本次不增加界面上的“一键全卸载”。交互删除必须先展示所选组件、实例、具体路径及配置影响，再输入 `DELETE`。保留维护者非交互的 `--apply --yes` 显式执行方式，但同时要求明确 `--components`；缺少组件范围即返回 `2`，不把默认全候选预览升级为全量删除。TUI/helper/npm 不自动添加执行或跳过确认参数。

### 安装时自动配置版本切换

安装成功标准包括多版本登记、Shell 加载、默认值和切换验证。用户无需自己编写切换函数、编辑 `PATH` 或手动维护启动配置。安装器负责生成配置，结果页负责告诉用户怎么使用；仅打印一段待用户自行安装的函数不算完成配置。

**Gradle** 使用现有独立版本目录及受管环境模块。安装程序在 `${ENV_FILE%/*}/gradle.sh` 中生成 Bash 3.2/Zsh 兼容、可长期加载的 `gradle_use` 函数，保留 `GRADLE_4_5_1_HOME`、`GRADLE_6_8_HOME` 对已验证安装的映射。该函数随受管环境聚合文件加载，不依赖 helper 的临时下载目录，不需要再次联网、下载工具包或重跑安装器。

| Gradle 命令 | 行为 |
| --- | --- |
| `gradle_use --list` | 显示已登记可用版本、当前终端活动版本及持久默认版本 |
| `gradle_use 4.5.1` / `gradle_use 6.8` | 在当前 Shell 更新 `GRADLE_HOME` 和 Gradle 的 PATH，只影响本终端及其后续子进程 |
| `gradle_use 6.8 --default` | 保存新终端的默认版本，同时切换当前终端；另一版本同样支持 |
| `gradle --version` | 核对实际使用的 Gradle 版本 |

持久默认值保存到 `GRADLE_DEFAULT_FILE`，默认 `${ENV_FILE%/*}/gradle-default`。文件只包含已登记的白名单版本字面量，按数据读取，不使用 `source` 或 `eval`。默认保存采用临时文件和原子替换，拒绝符号链接及异常目标；目标无效或保存失败时不改变当前终端环境，不报告切换成功。

切换前验证目标目录、可执行文件和对应 launcher JAR，验证失败保留原值。更新 PATH 时清除已登记 Gradle 版本及先前受管活动版本的确切 `bin` 项，再插入目标版本，并刷新 Bash/Zsh 的命令缓存；不累积旧版本路径，不破坏 Java、nvm 或其他 PATH 项的内容和相对顺序。切换不下载、不删除缓存、不改业务项目的 Wrapper 或 IDEA 已有 Gradle 设置；项目仍按其自身分发配置执行。

安装登记与默认激活分开。多版本先逐版验证并登记，所选安装全部验证通过后，按预先确定的规则一次写入默认值和加载配置；部分失败不将失败版本设为默认，保留已有有效默认。单版验证核对各自安装路径，最终环境验证核对计划中的默认版本，不能要求两版安装后 `GRADLE_HOME` 同时等于两套路径。新终端加载时只读取配置并选择已登记版本，不启动 SDK 做探测，也不下载缺失版本。

**Node.js** 始终由 nvm 进行版本选择，程序不另做一套 Node PATH 切换器或 node/npm 全局软链接。程序把已验证版本安装到 `NVM_DIR/versions/node/`，配置正确的 `NVM_DIR` 与 nvm 加载区块；Zsh 默认使用 `${ZDOTDIR:-$HOME}/.zshrc`，Bash 默认使用 `$HOME/.bash_profile`，显式配置 `SHELL_PROFILE` 时以其为准，并记录实际写入位置供后续清理。重复安装只更新相应区块。安装及版本切换中的默认值通过 `nvm alias default` 管理，不另写一套别名设置实现。

| nvm 命令 | 行为 |
| --- | --- |
| `nvm ls` | 查看实际已安装版本及当前/默认版本 |
| `nvm use 10` / `14` / `18` / `22` | 在当前终端切换到对应已安装 Node 版本 |
| `nvm alias default 14` | 设置新终端默认 Node 版本；不表示当前终端立即切换 |
| `nvm use default` | 让当前终端立即使用默认版本 |
| `node -v`、`npm -v` | 核对当前实际版本及配套 npm |

本工具安装集合仍为 10/14/18/22，但不限制用户通过 nvm 使用其他既有版本。全量、单版和 nvm-only 的默认值规则沿用前文。选择安装 Node 时，程序在隔离验证 Shell 中执行 nvm 加载、`nvm use`、命令路径及版本检查；nvm-only 则用 `--no-use` 加载并验证 nvm 本身，允许尚无 Node，不执行版本切换或修改已有默认。对应验证失败时不把配置报告为完成。采用 nvm 官方的当前会话和默认别名语义，见 [nvm 使用说明](https://github.com/nvm-sh/nvm/blob/v0.40.8/README.md#usage)及[默认版本说明](https://github.com/nvm-sh/nvm/blob/v0.40.8/README.md#set-default-node-version)。

helper 和 TUI 是启动终端的子进程，不能修改父 Shell 的环境。完成提示明确区分“已配置新终端默认值”“已在验证进程中验证”和“当前终端需要加载”。程序自动写好持久配置，用户新开终端即可使用；需要在原终端立即使用时，展示按实际路径安全引用的加载命令，不声称父终端已经切换。

### 安装完成后的切换指引

TUI 结果页与 CLI 完成输出必须列出实际成功安装的版本、有效默认版本、环境加载方法和可复制的切换命令，并写入本次安装报告。指引随安装结果生成，不能展示未安装版本为“可以切换”；重复安装或复用也输出指引。只安装 nvm 时说明“本次未安装 Node”，展示加载和 `nvm ls`，按实际状态列出既有版本和默认值；确实没有版本时才提示尚未安装，不虚构默认版本。

以下为两版 Gradle 均成功安装时的默认路径示例；程序实际输出使用解析后的 `ENV_FILE`：

```bash
# 当前终端先加载一次；也可直接新开终端
source "$HOME/.config/java-dev/env.sh"

gradle_use --list
gradle_use 4.5.1
gradle_use 6.8
gradle_use 6.8 --default
gradle --version
```

以下为四版 Node 均成功安装时的默认路径示例；程序实际输出使用已配置的 `NVM_DIR`：

```bash
# 当前终端先加载一次；也可直接新开终端
export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"

nvm ls
nvm use 10
nvm use 14
nvm use 18
nvm use 22
nvm alias default 14
nvm use default
node -v
npm -v
```

安装页上的版本选择决定“安装哪些版本”；安装完成后的 `gradle_use` / `nvm use` 决定“当前终端使用哪一版”。切换已安装版本无需重新安装软件或重新运行 helper。

### 按组件卸载必须进入执行层

当前卸载器总是扫描 JDK 与 Gradle，部分配置清理会删除整段 Java 受管配置，因此不能只在 TUI 隐藏未选项。新增 `--components` 后，扫描、计划、配置修改、进程退出请求和实际删除都只针对明确选中的组件。只卸载 JDK 必须保留 Gradle，提示依赖可能失效；只卸载 IDEA 不得顺带清理独立 JDK/Gradle。

实例选择必须传入执行层：清理计划为每个候选记录组件、规范化路径、来源证据及对象身份，TUI 将选中的实例白名单交给卸载器复核，重新扫描不能扩展为该组件的全部实例。现有 `--jdk-dir`、`--gradle-dir`、`--idea-app` 只是额外发现路径，不能冒充排他的选择过滤器。非交互按所选组件生成候选范围，并输出完整执行清单；按实例筛选的内部计划必须同样经过路径与来源验证。

IDEA 配置和插件只清理与选中应用明确关联、且未被保留 IDEA 实例共享的目录；共享或关联不明则保留并说明。现有 `--include-idea` 的全版本数据扫描必须改为受选择范围限制，不能为了删除某个 IDEA 实例而清理其他版本数据。

JDK/Gradle 的配置清理按组件与版本拆分，只移除所选对象对应的变量、PATH 和加载引用；共享文件中的其他工具配置保持不变。Gradle 卸载同步更新版本登记和 `gradle-default`：默认版本被移除时，只有用户在计划中确认了保留版本的切换才更新默认，否则清空失效默认并提示选择；只删非默认版本不改有效默认。保留其他版本的映射和切换函数；最后一版移除后清理本工具的 Gradle 函数、默认数据及加载配置，保留 JDK 和用户自定义内容。已经打开的终端不会被卸载子进程改写，结果提示新开终端或重新加载。清理不执行被卸载的 SDK。

前端卸载是本次新增能力，使用现有 Python 卸载器的计划、复核、确认和日志框架统一实现，不另起一套不受审核的递归删除脚本：

- **nvm 和 Node**：nvm 与每个 Node 版本有独立来源标记。不能因根目录有标记就删除其中所有版本、别名及全局包。计划逐项列出版本、来源和连带内容，受管 Node 版本删除会连带该版本全局包，必须在确认范围中明确说明。外部版本或未知内容存在时保留它们及所需 nvm 加载配置；无法安全删除整个管理器时标为“部分保留”，不报告 nvm 已全部卸载。默认别名指向待删版本时，将移除或改指的具体操作纳入确认计划，不静默重置用户默认版本。
- **Oh My Zsh**：框架、两个外部插件分别认领，检查外置 `ZSH_CUSTOM`。用户主题、自定义插件和其他额外内容保留；无法证明整根目录可删时不整根递归删除。只有框架确实卸载时才移除对应加载区块；保留框架或插件时使剩余配置仍有效，不用历史 `.zshrc` 备份覆盖现有配置。
- **iTerm2**：当前外置收据只有资源版本和摘要，缺少实际应用路径及身份，不能单凭旧收据认领现存应用。新安装收据需记录目标绝对路径、应用标识、版本及安装后可复核的代码身份；不向签名应用内部写标记。旧收据不能确认归属或应用已被替换时保留并说明。运行中的 iTerm2 不自动退出；若 helper 正运行在其中，要求从其他终端重试，不能关闭自己的宿主会话。

前端配置按安装记录的实际 Shell 文件处理：nvm 只修改对应文件中的 `team-frontend-env nvm` 区块，覆盖 Zsh、Bash 或显式 `SHELL_PROFILE`；Oh My Zsh 仍处理 Zsh 配置中的 `team-frontend-env terminal-tools` 区块。保留其他内容及备份，记录不完整或文件发生不明变化时保留并说明。安装复用的外部工具不会被补写“本工具安装”标记。预览中显示“可删除”“保留”“阻断”及原因，实际操作前复核路径、来源和确认范围，范围变化需重新确认。

## 安装任务进度条

### 展示样式

安装执行页展示总组件进度、当前组件和阶段进度，下方保留可滚动日志。以下为布局示例，实际值来自任务事件：

```text
安装并配置全部工具

已验证完成 2 / 6    [████████░░░░░░░░░░░░░░░░] 33%
当前：nvm / Node 18 · 下载安装包
下载 42 / 60 MiB   [█████████████████░░░░░░░] 70%

✓ JDK       ✓ Gradle       ● nvm
○ iTerm2    ○ Oh My Zsh    ○ IDEA/插件

Esc 取消任务                         日志可滚动
```

使用主题适配的颜色和明确状态文字；成功、失败、取消、等待、依赖跳过不只靠颜色区分。进度条宽度随窗口调整，窄窗口优先保留组件名、阶段与完成数量；过小时沿用扩大窗口提示，不能出现被裁切的确认操作。

### 进度的含义

| 进度层级 | 数值来源 | 展示规则 |
| --- | --- | --- |
| 总组件条 | 固定计划中已验证完成的组件数 / 总组件数 | 明确标注“已验证完成”，表示工作项数量，不代表耗时比例或剩余时间 |
| 下载条 | 当前下载尝试已接收字节 / 本次响应可信总字节数 | 总量有效时显示百分比；多个资源分别展示，不把某个文件当作整个组件进度 |
| 未知长度下载、解压、复制、配置和验证 | 实际阶段开始/结束事件 | 显示持续运动的条形指示与阶段名称；没有真实计量时不显示虚构百分比 |

已有安装只有复验通过才计入完成数；缓存命中后验证摘要通过，下载阶段显示“已复用缓存”。下载达到 100% 仅代表该文件传输结束，组件还要经过校验、安装、配置及验证，才能推进总组件条。组件只部分完成时总数不增加。

失败、取消、待处理或依赖跳过的组件不计为已验证完成，任务结束后不强制填满进度条。列表保留每项最终状态和失败原因；成功进程退出但未收到必要验证完成事件时显示状态待核实，不根据退出事件猜测所有步骤都成功。重试是新一次尝试，显示“正在重试”并重置该次下载进度，不累计失败尝试的字节。

### 事件与执行链路

现有 `@@TEAM_TUI` 仅包含阶段 ID、状态和标题，没有任务总量或字节数。新增任务计划和下载进度事件，保留旧阶段事件可读；旧脚本未提供总量时显示动态条，不能用“已收到的阶段数”作为分母。

安装选择变化时更新当前页的范围摘要；按 Enter 后、安装前固定内部计划，包含组件 ID、顺序、依赖、版本、子任务和目标目录。统一调度器执行前复核，若目标或范围与刚展示的选择不一致，则返回选择页说明变化，等待用户再次按 Enter，不静默扩大操作范围，也不增加常规确认页。资源缓存复用可改变阶段状态，不改变本次固定组件分母。组件 ID 与子任务 ID 分开，使用组件前缀避免多个 `step-1` 相互覆盖。

进度事件携带所属组件、资源 ID、尝试编号、阶段、已完成字节及可选总字节。下载器按实际响应决定总量，重定向、缺少长度、压缩或总量不可信时退回动态条；不得根据预设时长或单独 HEAD 响应猜测当前传输进度。具体采集方式在实现中围绕现有系统 curl 验证，不为进度引入 Python/Node 成员依赖。

进度事件按约 200 毫秒节流或合并；UI 队列满时可合并旧进度值，但任务计划、组件终态与最终退出事件不得被丢弃。非法、负数、越界或过期尝试的数据不能推动进度；日志控制字符继续清洗。`TEAM_TUI_EVENTS=1` 才输出协议，普通 CLI 仍输出普通日志。进度显示不得改变真实退出码、校验规则或进程组取消行为。

覆盖成员的全部软件下载路径：JDK、Gradle 的独立 curl 下载，以及 IDEA、插件和前端工具经 `prepare-resources.sh` 的下载。启动 helper 获取完整工具包时尚无 TUI，可显示简短阶段和 curl 原生传输进度；不把这段启动下载计入软件安装总组件条。服务端维护者下载器不在本次成员安装进度改造范围内。

## 成员使用方式

成员保存文件后，在文件所在目录执行以下命令；也可以在终端输入 `bash `，再拖入下载文件生成其完整路径。

```bash
# 打开首页，选择安装或卸载及具体组件
bash devtool-helper.sh

# 直接进入安装配置主界面或安全卸载页
bash devtool-helper.sh install
bash devtool-helper.sh uninstall

# 按组件选择前端工具，同样使用 install
bash devtool-helper.sh install --components nvm,iterm2,oh-my-zsh

# 预选全部六类工具；交互终端按 Enter 即开始安装
bash devtool-helper.sh install --components all

# 选择具体组件及版本
bash devtool-helper.sh install --components jdk,gradle --gradle-version 6.8
bash devtool-helper.sh install --components nvm --node-version none
bash devtool-helper.sh install --components nvm --node-version 22
bash devtool-helper.sh install --components nvm --node-version all

# 只预览所选组件的卸载范围
bash devtool-helper.sh uninstall --components nvm,iterm2,oh-my-zsh --dry-run

# 下载并校验最新工具后，只预览卸载清单
bash devtool-helper.sh uninstall --dry-run

# 显示本地帮助，不联网
bash devtool-helper.sh --help
```

标准运行方式使用 `bash`，不要求成员先执行 `chmod +x`，浏览器是否保留执行位不影响这一方式。服务端仍把生成文件设为 `0755`，便于已有执行权限时使用 `./devtool-helper.sh`。文档不推荐使用 `sh devtool-helper.sh`，因为实现使用 Bash 语法。

维护者交付的脚本内置服务器地址。环境变量 `SERVER_ADDR` 和 `SERVER_SCHEME` 继续允许临时覆盖；本次不增加脚本的 `--server` 或 `--scheme` 参数。已有 npm CLI 的同名参数继续有效。

## 命令与参数契约

### 操作选择

| 调用 | 行为 |
| --- | --- |
| 无参数，输入与输出均连接交互终端 | 下载校验后进入 TUI 首页；不会自动执行安装或卸载 |
| `install [业务参数…]` | 进入安装选择页；指定 `--components` 时直接预选，按 Enter 预检并执行，展示进度，不另设确认页 |
| `uninstall [业务参数…]` | 进入卸载选择页；指定组件时预选，生成准确计划后保留删除确认；无 TTY 且未明确申请执行时只预览 |
| `help`、`--help`、`-h` | 显示统一入口帮助，返回 `0`，不联网、不创建临时目录，不依赖有效服务器地址 |
| `help install`、`help uninstall` | 显示脚本内置的对应操作说明和常用示例，不联网；不复制完整业务参数解析器 |
| 未知子命令、未知顶层选项或非法帮助目标 | 提示错误和用法，返回 `2`，不下载 |

公共选择参数为 `--components jdk,gradle,nvm,idea,iterm2,oh-my-zsh`，支持任意非空子集或单独的 `all`。重复项去重，未知项、空项或 `all` 与其他项混用报用法错误。`install --components all` 始终覆盖六类；只安装前端工具同样使用 `install --components nvm,iterm2,oh-my-zsh`。`uninstall --components all` 只能按完整预览和确认流程操作，不是免确认删除命令。

helper 和 npm 均移除 `frontend` 子命令、`help frontend` 帮助目标及公共 `--frontend` 别名，不做兼容转发。旧写法在联网前返回 `2`，提示使用 `install --components ...`。TUI 移除独立前端筛选入口，所有工具在同一安装页选择；内部 `frontend-env.sh` 等已有文件可继续复用，不因此改名或再次暴露为公共入口。

`--gradle-version 4.5.1|6.8|all` 配置所选 Gradle 版本，`--node-version none|10|14|18|22|all` 配置 nvm 安装范围，其中 `none` 表示仅安装 nvm，`all` 表示安装 Node 10、14、18、22。`--node-version 16` 不再是有效的新安装参数。与未选组件无关的版本参数报错，不默默扩展安装或删除范围；`--node-version` 本次用于安装，卸载在清理计划中按已发现实例选择。省略 --node-version 时默认14，全量与安装页默认也选择14.21.3；显式 all 才安装四版。默认别名规则以本设计的“一键安装配置全部”为准。

业务参数写在操作名后，例如 `install --components jdk`，不自动把裸参数当作安装操作。停止维护旧下载器的裸参数兼容模式。组件安装不执行业务项目构建；现有带 `--project` 的项目检查/构建命令继续保留在维护者执行层，不属于新公共组件菜单。

`--plain` 在 helper、npm 和包内执行适配器中均不再支持。出现独立的 `--plain` 参数时返回 `2`，提示使用交互终端或明确业务命令；不静默去掉该参数后执行默认操作。公共入口与 npm 在联网前拒绝它，重复出现也同样处理；帮助和预演不构成启用文本模式的例外。

除帮助和预演外，无 TTY 的安装必须明确传入有效 `--components`；无参数调用或只给版本等其他选项均返回 `2`，不等待输入、不下载。显式选择后允许批处理执行，输出普通日志和真实退出码。卸载非交互默认只预览，真正删除仍要求原有显式执行与确认参数，并限定在所选组件；helper/npm 不自动补入它们。

TTY 下带组件参数的安装调用在 TUI 中预选，当前页按 Enter 即开始执行，不因提供参数而退回旧文本菜单；卸载仍进入删除清单与确认流程。业务 `--help` 与 `--dry-run` 例外，直接显示帮助或只读计划，不进入选择界面。外壳只解析动作、本地帮助/预演及必要的入口约束；组件计划与完整业务校验在工具包统一调度层完成，TUI 与 CLI 使用同一计划规则。

### 帮助与预演

将启动器预演和业务预演明确区分：

| 调用 | 是否下载工具包 | 输出与副作用 |
| --- | --- | --- |
| `--dry-run` 或 `--dry-run install` | 否 | 展示当前服务器、release.json/TAR 地址、内部统一入口和待转发参数 |
| `--dry-run uninstall --components idea` | 否 | 只展示将转发到卸载器的参数，不扫描电脑或删除文件 |
| `install --dry-run` | 是 | 下载校验后预览六类组件的默认安装计划；不安装、不构建 |
| `install --components jdk,gradle --dry-run` | 是 | 预览指定组件、版本、依赖补入和目标目录 |
| `uninstall --dry-run` | 是 | 下载校验后预览六类候选及保留原因，不删除 |
| `install --help` 或 `uninstall --help` | 是 | 取得最新完整工具的业务帮助 |

全局 `--dry-run` 只在操作名之前解析；未给出操作时按 `install` 展示目标。操作名之后的 `--help`、`--dry-run` 均属于业务参数，不被外壳截获。全局预演需要验证服务器配置，但不检查下载命令或创建下载目录。

保留参数中的中文、空格、单引号、换行及字面量 `$(...)`，使用参数列表调用，禁止拼接命令字符串或 `eval`。命令解析以首个操作名为边界，外壳不全局搜索任意位置的帮助或预演标记。

### 退出与取消

启动器自身的用法错误返回 `2`；不支持的平台、缺失依赖、下载、校验或解压失败返回非零并说明阶段。业务程序启动后保留其实际退出码，不把失败、取消或预览统一改为成功。

继续保留下载阶段的 INT、TERM、HUP 退出处理与临时目录清理。前台业务启动后，Ctrl+C 由现有 TUI 或卸载器处理，外层等待其真正结束再清理；不能因外层提前退出而删除正在使用的临时工具包。保留现有 TUI 卸载中断后返回结果页的行为。

helper 和包内执行适配器不保留专为 Finder 双击准备的“按回车关闭”停留，结果仍由 TUI 结果页或终端输出呈现。卸载问答扩展到所选六类组件，最终 `DELETE` 确认及取消机制继续保留。仅向包装层 PID 发送信号与终端中断前台进程组不同，验收须覆盖现有 npm 终止链路，不宣称已有 trap 能自动处理任意进程树。

## 实现结构

将唯一下载模板重命名为 `tools/devtool-helper.sh.in`。公共脚本和新 npm 包均由它生成或渲染，使用同一套子命令、下载、校验和解压实现，不保留旧下载器的兼容模式。

模板只需 `@SERVER_ADDR@`、`@SERVER_SCHEME@` 两个构建期占位符。删除 `@ENTRY_NAME@`、`@ENTRY_LABEL@` 及双入口渲染逻辑；目标固定为包内 `.support/scripts/run-tool.sh`，只传固定动作和业务参数，不通过保存文件名推断操作，也不让输入直接拼接执行路径。

共用流程为：校验服务器配置和平台 → 检查系统命令 → 创建临时目录 → 下载并解析 `release.json` → 下载固定路径 TAR → 按发布清单校验大小及 SHA-256 → 验证归档路径及成员类型 → 解压 → 验证统一入口 → 用 `/bin/bash run-tool.sh install|uninstall ...` 启动 → 等待结果并清理临时目录。

使用 macOS 自带 `plutil` 读取发布清单的固定字段，不增加 Python、Node 或 jq 依赖。限制清单大小，检查 schema、固定路径、摘要格式及大小类型；不执行 JSON 内的内容，不接受清单改变已配置服务器或指定任意下载地址。清单与 TAR 下载期间版本发生变化并导致不一致时停止并提示重新运行，不回退到旧摘要文件或未验证包。

保留现有协议限制、超时、错误地址提示、归档越界与链接拒绝规则。校验未通过、统一入口缺失或卸载程序损坏时直接失败，不回退为安装。每次正常运行都获取最新完整工具包；helper 本身不自动更新，入口协议改变时需要重新下载。

macOS 平台检查放在实际下载运行之前；本地帮助和启动器预演可以在其他平台阅读。包内卸载仍使用自带运行时，不转到需要系统 Python 的维护者入口。

删除 `dev-kit/.support/menu.sh` 及两份 `.command` 包装器；打包白名单也移除这些文件和 `使用说明.txt`，加入统一 `run-tool.sh`。新入口保留 TTY/组件参数/帮助/预演路由、退出状态和信号处理，不剥离 `--plain` 后执行默认操作。`run-tui.sh` 和 Go CLI 增加安装页及预选组件/版本的传递规则；界面异常时提示修复并退出，不恢复文本交互或直接执行安装。

新增 `dev-kit/.support/scripts/manage-components.sh` 作为组件安装计划与队列调度入口，统一组件标识、默认值、依赖去重、预检、固定任务 ID、执行顺序和汇总。它复用 `repair-env.sh`、`frontend-env.sh` 与原组件脚本；需要将旧聚合器中会重复处理依赖或隐式扩展范围的步骤拆到共同调度边界，不能简单串联两个 `all`。TUI 负责选择和呈现，不能自己实现另一套安装顺序或用多个独立作业拼出总百分比。计划以结构化数据供选择页就地显示及执行层复核，不解析人类日志，也不要求独立预览页；实现时固定计划字段并测试按 Enter 前展示范围与执行范围一致。

卸载继续使用 `tools/uninstall_java_gradle.py` 作为唯一维护源码，在其扫描与计划层加入组件筛选、前端归属及独立配置清理；`run-cleanup.sh` 调用打包运行时。历史文件名本轮可以保留，帮助与文档更新为六组件卸载，不另复制一份前端删除实现。

Go 和卸载器源码都发生变化，因此必须重建 arm64、amd64 两个 TUI 文件以及 universal2 卸载运行时，更新各自 manifest，再显式生成配套运行文件发布 ZIP 和锁。成员 start/package 不生成该运行文件 ZIP；有效运行文件复用，缺失或过期才按锁下载。正式部署前，对应 Release 必须可下载或已离线准备，不能只更新锁却缺少资产。

## 最少发布产物与生成规则

新文档、维护者就绪输出和成员操作说明统一使用 `devtool-helper.sh`。停止生成和托管旧双下载器、`start.zip`、`team-dev-env.zip` 及工具包单独摘要文件，不提供备用压缩格式或旧地址转发。

```text
dist/server/
├── devtool-helper.sh                 # 新成员统一入口
├── release.json                      # 版本、入口及 TAR 的摘要和大小
├── dev-env/
│   └── team-dev-env.tar.gz            # 唯一工具压缩包
└── resources/                        # 仅在显式要求部署资源副本时产生
```

`PUBLICATION_ARTIFACTS` 只包含 `devtool-helper.sh` 和 `dev-env/team-dev-env.tar.gz` 两个实体文件，`PUBLISHED` 加上 `release.json` 后总计三个固定发布文件。软件资源文件不计入这个控制文件数量，但部署时仍按资源清单逐项校验。三个文件均禁缓存，缺失或摘要不一致时 `serve` 拒绝启动。

### 一份清单提供发布信息和工具校验

发布清单升级为 `schema=2`，保留 `interface=go-tui`、发布时间、服务器信息、TUI/cleanup 源码摘要及 `go-tui-<TAR 摘要前 12 位>` 版本规则。以 `launcher` 和 `bundle` 两个固定对象替代旧 `artifacts` 集合，分别只有 `path`、`size`、`sha256` 字段；路径固定为 helper 和现有 TAR 路径。客户端可直接读取 `bundle.sha256`、`bundle.size`，不必解析含点号的动态文件名键。

服务端验证两个对象路径精确匹配、size 为正整数、sha256 为合法摘要，并与实际文件及版本字段一致。helper 下载 TAR 时使用 bundle 的摘要与大小；launcher 摘要用于服务端发布核对，不要求成员已保存的旧 helper 与服务器新脚本摘要一致。清单不信任任意地址字段、不放宽运行文件来源验证；不另生成清单摘要文件，TAR 内仍保留运行文件 manifest 和第三方许可。

`start`、`serve`、`preview` 及 `package` 的就绪或交付提示改为新脚本链接与运行说明。支持版本查询参数，例如 `/devtool-helper.sh?v=go-tui-…`；版本参数只用于标识工具包，不能替代禁止缓存。原默认端口、LAN 地址发现和服务器配置规则不变。

对脚本下载响应增加 `Content-Disposition: attachment; filename="devtool-helper.sh"`，确保浏览器按固定名称保存。保留现有 `Cache-Control` 和条件缓存请求处理，查询参数不得影响这些响应头。实际使用外部静态服务器或反向代理时，在部署文档说明需要等效的脚本下载和缓存配置。

新服务端和 helper 使用 schema 2，会拒绝旧清单。升级必须重新生成三个发布文件，并向成员提供新 helper；仅删除旧 ZIP 或把 helper 拷入旧目录不构成有效升级。正常更新功能工具时仍重新发布 TAR 和清单，兼容 schema 2 的 helper 每次取得最新版本。

### 其他产物按需生成

| 操作或文件 | 生成规则 |
| --- | --- |
| `package` / `start` | 只在一个最终输出目录生成上述三个文件；不生成备用工具 ZIP、摘要副本、额外说明、版本快照目录或 npm 包 |
| SDK 与软件资源 | 本地资源库保留固定源文件及必要来源记录。普通本地 start/serve 从已验证资源目录只读映射资源请求，不复制一套；部署外部静态服务器时显式 `--with-resources` 才复制必要软件文件 |
| 发布资源摘要 | 摘要已在 TAR 内的 `resources.tsv` 中，静态发布副本不额外生成每个资源的 `.sha256`。维护者资源库及成员下载缓存中用于归属/复用的记录保持其原用途 |
| `preview` | 默认使用系统临时目录及只读资源映射，结束后清理；不反复创建 `dist/*-preview` 或覆盖正式发布地址。显式传入输出目录时才保留该目录供调试 |
| TUI/cleanup 构建 | 仅源码变化或明确要求构建时更新固定的 `resources/tui/`、`resources/cleanup/`；保留架构文件、manifest 和许可，不生成另一套成员备用包 |
| 运行文件 Release | 仅显式 `release-runtimes` 生成一个 `team-dev-env-runtimes.zip` 并更新 `resources/runtime-lock.json`。ZIP 摘要已有锁记录，不再默认生成旁置 `.sha256`；发布说明供命令输出或临时发布步骤使用，不默认落盘 `release-notes.md` |
| npm 包 | 保留能力但只在维护者显式 `npm pack` 时产生一个包；常规成员发布不顺带执行，不追加历史 tarball 副本 |
| 使用文档、测试、缓存、构建中间文件 | 文档留在仓库或交付页面，TAR 不重复包含；测试/构建缓存不入包并使用系统临时目录。为原子替换可在目标文件系统就近暂存，完成或可处理失败后清理；未完成恢复所需数据仅在报错时明确保留路径，不作为正常产物 |

完整工具 TAR 仍需包含全部功能脚本、两架构 TUI、自带卸载运行时、配置及来源/校验清单。许可证、用户环境状态、安装归属收据与任务日志具有实际用途，不把它们作为干扰文件删除；它们保存在对应内部或用户目录，不额外铺到成员发布根目录。

`serve/preview` 补齐资源目录读取选项，沿用 `--resources-dir` 的含义：优先显式参数，其次发布目录 resources，再用服务器配置，最后使用仓库资源库。读取 TAR 内资源清单确定可提供的资源；映射不通过符号链接实现，路径与文件摘要按该清单校验，历史发布不用当前源码清单替代。公开 HTTP 只允许三个发布文件及清单中的软件资源，关闭目录列表，其他文件即使留在磁盘也不暴露。外部静态服务器配置等效的资源映射/部署规则和访问范围。

### 已有发布目录的清理

当前 `package()` 保留未知文件，HTTP 服务也不以 `PUBLISHED` 限制所有下载。必须同时处理磁盘残留和 HTTP 暴露，不能只从产物常量中删除名称。

1. 新目录不生成退场文件。复用输出目录时检查固定集合：`start.command`、`uninstall.command`、`start.zip`、`team-dev-env.zip`、`dev-env/team-dev-env.tar.gz.sha256`；若存在链接或非普通文件则失败，不追随或删除它们。
2. 先在暂存目录生成并校验全部新产物，再按现有发布流程替换新文件。新文件与清单校验通过后，删除前述固定集合中仍存在的普通文件。准备或校验失败不清理旧文件，不删除未知文件或资源目录。
3. 清理失败返回非零，不输出发布成功或启动下载服务；提示维护者处理明确路径后重试。发布并非整个目录的原子事务，失败后需重新核对当前文件和清单，不能宣称已自动完整回滚。
4. `serve` 校验三个发布文件并拒绝固定退场文件残留。HTTP 按固定发布/资源范围提供文件；旧 ZIP、旧下载器、旁置工具摘要和单独 `.command` 请求返回 `404`，覆盖 GET、HEAD、查询参数和编码形式，目录列表关闭。运行后被复制进的无关文件也不进入下载范围。
5. 外部静态服务器部署优先使用全新发布目录后切换；如复用目录，必须确认旧文件已删除，并配置等效的访问限制和目录索引规则。升级前停止旧服务，避免旧进程继续暴露旧地址。

迁移只处理明确列出的旧发布文件，不清空未知文件或历史测试目录；不删除成员已保存文件。成员需要新的 helper 或重新打包的 npm 包；旧 `.command`、ZIP、摘要协议和 `--plain` 不再作为兼容方式。旧资源旁置摘要不作为新资源路由，不能通配删除源资源库中的来源记录。

## npm 入口适配

`npm-cli/scripts/prepare-package.cjs` 改为把新模板复制到 `assets/devtool-helper.sh.in`，并清理本包 assets 中固定的旧 `start.command.in`，避免已生成目录将两份模板一起装入新包。`npm-cli/bin/team-dev-env.cjs` 同步调整模板查找、占位符与临时文件名，只向脚本显式传入 `install` 或 `uninstall` 及业务参数。

删除 npm 的 frontend 动作、专用帮助和 `--frontend` 注入逻辑，本地预演直接展示 install/uninstall 及所选组件。安装 nvm、iTerm2、Oh My Zsh 与其他组件共用同一参数和执行链路。保留 npm 前缀环境隔离、终端继承、进程终止传递和临时文件清理。

npm 的 `--server`、`--scheme` 仍由 Node 层处理，现有 `--help`、`--dry-run` 保留本地帮助和启动器预演含义。同步使用新的 `--components` 与版本选项，删除并在联网前拒绝 `--plain`；正常执行时，无 TTY 的安装必须显式选择组件，否则采用 helper 的返回 `2` 规则。TTY 下带组件参数的安装同样预选到选择页，按 Enter 即预检并执行，进入进度界面；卸载保留删除确认。帮助和启动器预演仍可无 TTY 执行，`--plain` 仍按已删除参数拒绝。迁移说明和测试须记录这些变化，不再承诺 npm 全部旧行为保持不变。

本地 npm 包需要重新 `npm pack` 才能包含新模板；不公开发布或更名 npm 包。`npm-cli/package.json` 已通过 `assets/` 目录规则收集模板，无须仅为文件改名调整包配置。

npm 启动器仍要求已有 Node `>=14.14`，不因增加 Node 10 安装选项而降低其运行要求。当前终端使用 Node 10 时，可通过 `bash devtool-helper.sh` 管理环境，或先切换到满足 npm 启动器要求的已安装版本。

## 需要调整的文件

### 实现和测试

| 文件 | 调整内容 |
| --- | --- |
| `tools/start.command.in` → `tools/devtool-helper.sh.in` | 重命名唯一模板，增加子命令与帮助/预演边界，移除旧下载器渲染协议 |
| `server/manage.py` | 只生成 helper、TAR、release.json；不输出独立摘要/ZIP/资源收据副本，按需映射或部署资源，临时预览及 HTTP 下载范围控制 |
| `server/publication.py` | schema 2 的 launcher/bundle 信息、实际摘要/大小及版本验证，拒绝旧字段和旧清单 |
| `dev-kit/开始配置.command`、`dev-kit/卸载环境.command` | 删除两份包装器，迁移到统一 run-tool.sh，移除文本模式和双击停留 |
| `dev-kit/.support/scripts/run-tool.sh`（新增） | install/uninstall 固定分流、安装 Enter 执行与卸载确认、TTY/CLI 参数约束及原信号/退出语义 |
| `dev-kit/.support/menu.sh` | 删除原数字交互菜单源码 |
| `tools/package-files.txt` | 移除两份 `.command`、menu.sh、使用说明；仅加入统一入口、实际功能、配置和必要内部清单/许可 |
| `dev-kit/.support/scripts/run-tui.sh`、`tui/main.go` | 统一安装选择页与组件预选，移除独立 frontend 页入口和文本降级提示 |
| `tui/actions.go`、`tui/ui.go` | 六组件选择、安装 Enter 执行、进度与结果；结果页展示实际已安装版本、默认值、加载及切换指引 |
| `tui/runner.go` | 结构化计划和下载进度解析，组件/子任务 ID 与重试识别，事件节流合并及关键终态保留 |
| `dev-kit/.support/scripts/manage-components.sh`（新增） | 统一安装计划、依赖和默认版本决策；多版本先登记再一次激活，汇总真实结果与切换指引 |
| `dev-kit/.support/install_env.sh`、`dev-kit/.support/scripts/repair-env.sh`、`dev-kit/.support/scripts/frontend-env.sh` | 接入组件调度，拆分必要的旧聚合边界，补齐依赖跳过及组件验证事件；维护者项目功能继续保留 |
| `dev-kit/.support/scripts/lib/common.sh` | 增加计划/组件/下载进度协议输出，保留开关及字段清洗 |
| `dev-kit/.support/scripts/lib/managed-env.sh`、`dev-kit/.support/config/env.sh` | 自动生成持久 `gradle_use`、登记映射和默认数据路径；同会话 PATH 切换及新 Shell 默认加载 |
| `dev-kit/.support/scripts/lib/environment.sh`、`dev-kit/.support/scripts/verify-environment.sh` | 区分逐版本安装验证与最终默认环境验证，避免多版本共存被判定为版本错误 |
| `dev-kit/.support/scripts/runtime/config-jdk.sh`、`dev-kit/.support/scripts/runtime/install-gradle.sh` | 下载/阶段事件及依赖去重；Gradle 注册和默认激活分离，验证函数后输出切换指南 |
| `dev-kit/.support/scripts/runtime/install-node.sh` | 四版及 nvm-only 安装；通过 nvm 设置/验证默认和切换，按实际版本输出使用指引，检查架构与 Rosetta |
| `resources/catalog.tsv`、`resources/frontend/node/` | 补齐 Node 10 x64、Node 22 arm64/x64 的固定资源与摘要，保留 14/18，从有效新安装清单移除 16；成员资源清单由打包生成 |
| `dev-kit/.support/scripts/software/install-idea.sh`、`dev-kit/.support/scripts/software/install-idea-plugins.sh` | 将 IDEA 软件和插件纳入同一组件计划，补齐阶段/验证信息 |
| `dev-kit/.support/scripts/software/install-iterm2.sh`、`dev-kit/.support/scripts/software/install-zsh.sh`、`dev-kit/.support/scripts/lib/frontend.sh` | 进度和收据；增强 iTerm2 身份记录，自动配置 nvm 的目标 Shell 加载区块，不覆盖用户其他配置 |
| `tools/prepare-resources.sh`、`dev-kit/.support/scripts/download-tools.sh` | 共享客户端下载进度采集与任务上下文传递；不解析 curl 人类日志伪造百分比 |
| `tools/uninstall_java_gradle.py`、`dev-kit/.support/scripts/run-cleanup.sh` | 六组件/实例筛选及前端来源；按版本维护 Gradle 登记/默认/函数、Node 默认引用与 Shell 区块，保留确认 |
| `npm-cli/scripts/prepare-package.cjs` | 复制新模板，清理 assets 中固定旧模板，避免新包夹带旧副本 |
| `npm-cli/bin/team-dev-env.cjs` | 仅 install/uninstall 动作，删除 frontend/--frontend 分支，拒绝 `--plain`，统一组件预演和帮助 |
| `tests/test_distribution.py` | helper 读取 schema 2 后校验 TAR 的大小/摘要及运行统一入口；包内无旧入口/菜单/说明，保留下载和取消覆盖 |
| `tests/test_server.py` | 三个发布文件及精简清单，五项旧文件退场；资源映射/显式复制、临时预览、访问范围和目录列表关闭 |
| `tests/test_npm_cli.py` | 新模板及组件参数；frontend/--frontend/help frontend 拒绝，保留 install/uninstall、本地预演与信号回归 |
| `tests/test_tui_entry.py`、`tests/test_cleanup_entry.py` | 改用 run-tool.sh 的 install/uninstall，移除旧菜单及双击停留用例，保留 TUI/CLI/信号及确认覆盖 |
| `tests/test_member.py`、`tests/test_frontend_env.py` | 删除专属数字菜单用例，将仍有效的预检、版本选择、日志及失败保护验证迁往 TUI 或执行层，保留组件安装测试 |
| `tui/actions_test.go`、`tui/runner_test.go`、`tui/ui_test.go`、`tui/ui_signal_test.go` | 六组件映射、批量计划及去重，进度真实性、事件高频与重试、窗口布局及取消 |
| `tests/test_tui_events.py`、`tests/test_resources.py`、`tests/test_gradle_install.py`、`tests/test_node_install.py`、`tests/test_terminal_tools.py` | 计划先于执行、进度、缓存复用与归属；Node 四版单选/all/none、架构、默认别名、旧版本保留与缺资源失败 |
| `tests/test_gradle_versions.py`、`tests/test_managed_env.py`、`tests/test_environment_verification.py` | 同一 Bash/Zsh 反复切换、当前/默认分离、新终端加载、双版复验、PATH 幂等与默认保存失败 |
| `tests/test_uninstall_java_gradle.py`、`tests/test_uninstall_interactive.py`、`tests/test_managed_env.py`、`tests/test_sdk_ownership.py` | 只删所选组件/实例、不破坏未选配置；前端归属、用户内容保留、iTerm2 宿主检测及确认范围复核 |
| `tests/test_component_plan.py`、`tests/test_frontend_cleanup.py`（新增） | 统一计划与一键全部，依赖失败和取消；六组件选择下的前端专门清理用例 |
| `resources/tui/`、`resources/cleanup/`、`resources/runtime-lock.json` | 重建双架构 TUI 与 universal2 cleanup，更新 manifest 和运行文件 ZIP/锁/Release |
| `tools/release-runtimes.py`、`tests/test_runtime_release.py` | 显式发布仅输出一个运行文件 ZIP 和源码锁；不默认写 ZIP.sha256/release-notes.md，验证锁覆盖摘要和来源 |

新模板是源码，`dist/server/devtool-helper.sh` 是生成文件，不能手改生成文件作为实现。`npm-cli/assets/` 同样由预打包步骤生成。

### 使用和维护文档

| 文件 | 调整内容 |
| --- | --- |
| `README.md`、`index.md` | 新成员下载和运行方式、统一安装/卸载示例、维护者链接 |
| `dev-kit/使用说明.txt` | 作为仓库文档更新，但不加入 TAR；说明安装结果中的版本切换指引 |
| `docs/distribution.md` | 三个发布文件、schema 2 校验、固定退场文件、内部入口及按需产物规则 |
| `docs/service-startup.md` | 本地只读资源映射、显式 --with-resources、默认临时预览和三个文件的部署验证 |
| `docs/resources/README.md` | 资源源库/发布副本用途，固定摘要留在资源清单，静态副本不另写 .sha256 |
| `docs/environment/README.md` | 环境文档的成员总入口 |
| `docs/environment/cleanup.md` | 六组件及实例选择、来源与配置边界、nvm 用户内容和 iTerm2 运行限制、预览与确认；移除“前端不在卸载范围”旧结论 |
| `docs/environment/tui.md` | 单一安装页、结果页切换指南、进度和运行文件要求；删除 frontend 页面及文本降级说明 |
| `docs/environment/frontend.md`、`npm-cli/README.md` | 移除 frontend 命令，改为 install 组件选择；nvm 自动加载、默认规则、切换示例与卸载说明 |
| `docs/resources/frontend-sources.md` | 更新 Node 10/14/18/22 的固定补丁版、架构、官方来源与 SHA-256 核验记录 |
| `docs/environment/runtime.md`、`docs/environment/gradle.md` | Gradle 多版登记/默认文件/自动函数，当前与持久切换、加载与卸载后生效范围；不再以重跑安装器作为切换方法 |
| `docs/environment/ide.md`、`docs/environment/dependencies.md` | IDEA 与插件组合范围、全量依赖预检和未满足条件的处理方式 |
| `docs/environment/runtime-release.md` | 成员三个发布文件，显式运行文件发布只生成 ZIP/锁；更新说明和上传命令，不依赖已删除的摘要或说明文件 |
| `docs/verification.md` | 实施完成后追加真实验证结果；历史结果不重写，也不预填通过数量 |

当前有效说明中的“普通模式”、数字菜单编号和 `--plain` 指引一并清理，包括资源指南中的旧菜单操作。`docs/plans/` 的旧实施计划及验证历史保留原貌；不得为了删除旧入口而篡改历史记录或误改服务端启动文件名。

### 保持不变的核心文件

| 文件或范围 | 原因 |
| --- | --- |
| `tools/package.sh`、`tools/preview.sh` | 当前只向 Python 管理器转发参数，没有固定启动 ZIP 逻辑 |
| `server/start-server.command`、`server/start-server.cmd`、`tests/test_start_entry.py` | 属于维护者服务端启动，不是本次成员入口 |
| `tools/build-tui.py`、`tools/build-cleanup.py`、`server/runtime_artifacts.py` | 更新必需产物；编译、运行文件锁及来源验证机制沿用，不因删发布副本而删除内部校验和许可 |
| `server/network_download.py` | 属于维护者准备资源的下载链路，不是成员安装进度的来源 |

内部入口、安装流程和运行文件仍需参加回归测试；“无需改动”不等于跳过验证。

## 验收标准

以下均为实施后的验收要求，本稿不代表已完成这些检查。

1. 新成员只需下载一个 `devtool-helper.sh`。通过 `bash` 可在没有 Node、Python、Go 和 Homebrew 的成员环境中启动；脚本移动、改名或置于含中文、空格、单引号的路径后仍可工作。
2. TTY 无参数进入首页；安装/卸载页均可选择六类组件，前端工具与其他工具共用 install。安装页及带参数预选页按一次 Enter，预检通过后立即执行；空选择、版本无效或预检失败时不执行。卸载保留清单确认，只静态扫描。helper/npm 的 frontend、help frontend 和 --frontend 在联网前被拒绝，TUI 无单独前端入口；不恢复旧文本菜单。
3. 本地帮助、全局预演、非法子命令、无 TTY 的空操作在受控不可达网络环境中仍按约定完成，不联网、不创建下载目录。有效业务预演只下载工具，不安装或删除组件。
4. install/uninstall 子命令只消耗一次，支持的组件及版本参数逐项保真，不再注入前端路由标记。`uninstall --dry-run` 到达卸载器，不能被误判为安装或仅输出 URL。任意公共入口、npm 或包内适配器收到独立 `--plain` 参数都返回 `2`，不吞掉参数后执行默认安装。
5. release.json 的 schema、固定路径、size/sha256 格式，以及 TAR 大小、摘要、归档和统一入口校验失败时均不执行。覆盖下载期间版本不一致、缺清单、错误服务器根目录、临时目录清理与每次获取最新包；不回退 .sha256 旧协议。
6. 六组件卸载按实际选择约束扫描、配置清理和删除；实例白名单不得扩展，只删 JDK 不动 Gradle、只删某个 IDEA 不动独立 SDK 或其他 IDEA 的数据。覆盖前端归属、用户内容、配置区块与 iTerm2 宿主保护。交互必须输入 `DELETE`；非交互须显式 `--components` 加 `--apply --yes`，外壳不自动补入这些执行参数或管理员权限。
7. 保留下载取消、TUI 前台中断、卸载取消后返回结果页、npm TERM/HUP 传递和真实退出码测试，不发生提前清理临时包、挂起或残留测试进程。
8. 常规 package/start 只生成 helper、TAR、release.json；schema 2 仅记录两个实体产物。固定五项旧文件不生成、不保留、不托管；迁移仅处理普通旧文件，保留未知文件及源资源记录。准备/校验失败不清理，清理失败不报告成功；serve 拒绝旧清单或退场文件残留。
9. Windows 风格 CRLF/BOM 输入仍被规范化，Python 打包不执行 Shell 或 Mac 二进制；helper 下载头包含正确文件名，带查询参数和条件缓存请求也取得新内容。Windows 实机结果与平台模拟测试分别记录。
10. HTTP 只提供三个固定文件与当前包清单中的软件资源；旧 ZIP/.command/工具摘要及未知文件 GET/HEAD 返回 `404`，查询参数、编码或后来复制进文件均不放宽范围，目录浏览关闭。外部静态服务器验证等效规则。
11. npm 本地包只含新模板，不含私有服务器地址或旧模板；保留本地帮助/预演含义，验证组件参数、`--plain` 拒绝及无 TTY 安装范围要求。双架构 TUI、universal2 cleanup 与源码摘要一致，配套运行文件 ZIP、manifest、锁及 Release 地址通过验证。
12. 首页选中一键全部后按一次 Enter，预检通过即执行六组件，无额外计划确认；执行范围在当前页可见，版本可在安装选择页提前调整。全量执行严格遵循 JDK → Gradle → nvm/Node → iTerm2 → Oh My Zsh → IDEA/插件，部分选择和自动补入依赖也保持该相对顺序。固定计划中 JDK 依赖去重，IDEA 插件和 Node 作为子任务，nvm-only 不下载 Node。预检不静默省略组件；失败只跳过受影响依赖，独立项继续，取消则停止后续全部项。
13. 总条只按固定计划中验证完成的组件计数，重复事件不重复累计；下载条仅在总量可信时显示百分比，未知总量及安装阶段显示动态条。传输 100% 不等于安装完成，失败、取消和待处理不补齐总条；重试、事件节流、小窗口及任务切换保持正确。
14. 高密度进度更新不能挤掉计划、阶段终态和退出事件，普通 CLI 不泄露协议。JDK/Gradle 及共享资源下载路径均有进度或明确动态阶段，进度采集不削弱摘要校验、取消和失败退出语义。
15. Node 10、14、18、22 均可单独选择，`all` 安装这四版，`none` 只安装 nvm；新安装拒绝 16，但不删除已有 16。验证 all/none 保留有效已有默认（包括 16）、安装页/一键全部/省略版本默认选择并安装14.21.3，显式 all 的首次或失效默认回退到14、单版（包括默认单14）默认所选版；nvm-only 无 Node 时仍可验证成功且不改别名。覆盖 10/14 的 x64/Rosetta、18/22 原生架构及缺资源/运行失败；将 `test_frontend_env` 原本拒绝 22 的用例改为接受 22、拒绝 16 新安装，保留历史版本卸载发现测试。
16. Gradle 安装后自动具备可持久加载的 `gradle_use`；同一 Bash/Zsh 中从 4.5.1 切到 6.8 再切回，命令路径准确且 PATH 无旧版本累积。普通切换不改默认，`--default` 同时影响当前和新终端；目标无效或写入失败保留原状态。双版默认由计划决定，不由安装顺序决定；卸载单版不破坏剩余版及 JDK。
17. Node 配置通过 nvm 完成，验证 `nvm use` 只改变当前会话，`nvm alias default` 供新终端加载，`nvm use default` 可应用默认；不新增 Node PATH 选择器。覆盖 Zsh/Bash/自定义 Shell 入口的加载与按记录清理、自定义 NVM_DIR、默认别名、重复配置及 Gradle/Node 相互切换互不破坏。
18. 安装成功或复用后的 TUI 结果、CLI 输出和报告均展示实际版本、有效默认、加载命令和切换命令；只安装一版不展示其他版本已可用，nvm-only 不假定有 Node。提示不能把子进程验证当作已改变父终端，切换不依赖已清理的下载临时目录。
19. TAR 无两份 .command、数字菜单、使用说明或 ZIP 副本，统一 run-tool.sh 保持安装/卸载路由与信号行为；manifest 和第三方许可仍完整。默认预览不写 dist 历史目录且退出清理，显式输出目录才保留。普通发布不生成 npm 或运行文件 ZIP。
20. 本地 start/serve 的资源只读映射不重复复制软件；显式 --with-resources 才部署必要文件，不另写发布资源摘要。运行文件发布只有一个 ZIP 和配套锁，摘要来自锁；校验、缓存归属、失败记录和许可证不因精简被削弱。

验证使用临时 HOME、临时服务目录和可控的模拟 SDK/卸载对象。运行入口、分发、npm、组件计划、安装、卸载及事件协议的相关回归和 Go 测试；原本使用 `menu.sh` 验证权限、源码缺失及符号链接保护的用例改用保留文件，不能直接删除安全覆盖。使用可控下载服务测试有/无长度、缓存、重试和取消，伪终端验证选择与进度。验证两类运行文件构建和发布链路，验收真实脚本帮助与预演，不对当前电脑执行实际安装或卸载。Shell 语法使用 Bash 3.2 检查。

## 实施边界与顺序

先固定六组件计划、版本配置和来源边界，再扩展安装调度与卸载；接着实现 TUI 选择和进度，整合 helper/npm 与统一内部入口。随后重建必需运行文件、落地 schema 2 及三个文件的发布、资源映射和退场规则，更新文档并完成隔离验收。正式部署需要对应运行文件 Release 已准备就绪。

本次扩展到六类工具的选择与卸载，增加全量安装配置和真实事件驱动的进度条；不新增 Linux/Windows 成员支持，不关闭 macOS 安全功能，不增加自动提权，不公开发布 npm 包，也不部署或覆盖团队线上服务。设计稿仅交付方案与文件影响清单；业务实现及构建产物在后续实施时调整。
