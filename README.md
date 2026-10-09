# 前端转型 AI 全栈计划

团队 macOS 开发环境工具，通过一个 **`devtool-helper.sh`** 入口安装、配置和卸载六类组件：JDK、Gradle、nvm/Node、IDEA、iTerm2、Oh My Zsh。团队学习安排见[转型推进方案](docs/roadmap.md)。

## 小组成员开始使用

1. 连接团队内网，下载维护者提供的 `devtool-helper.sh`，在终端进入下载目录，运行 `bash devtool-helper.sh`。无需克隆仓库、填写服务器地址或预装 Python、Node、Go、Homebrew。
2. 首页选择“安装与配置”，方向键移动、空格勾选组件、左右键选择版本。查看当前页的版本、目录、依赖和默认值影响，**Enter 直接预检并安装所选项**；空选择不执行，预检失败保留选择并说明原因。
3. 要安装全部工具，选择首页“一键安装配置全部”并按 Enter。默认安装 JDK 8、Gradle 4.5.1、nvm 和 Node 14.21.3、iTerm2、Oh My Zsh 与四个常用插件、IDEA 2025.3.6.1 与六个推荐插件。
4. 查看组件结果、日志和版本切换指引。新开终端加载配置；需要在原终端立即使用时，执行结果页提供的实际加载命令。保存工作并退出 IDEA 后再安装插件或修改 SDK 登记，安装后手动打开 IDEA 配置并同步业务项目。

全量与部分安装均按 **JDK → Gradle → nvm/Node → iTerm2 → Oh My Zsh → IDEA/插件** 执行。Gradle 会补入 JDK 8 依赖；仅选 IDEA 不隐式安装 JDK。全部所选组件验证通过才报告整体成功，失败的依赖任务会跳过，其他独立组件继续；取消会停止后续任务，已经成功安装的内容保留。成员流程不选择业务项目、不执行构建。

卸载使用同一个入口：`bash devtool-helper.sh uninstall`。卸载页默认全部不选，选择组件及具体实例后核对路径、配置影响和保留项，输入 `DELETE` 才执行。它静态识别来源，不运行待删除 SDK；组件选择会限制实际扫描、配置修改和删除。详见[卸载指南](docs/environment/cleanup.md)。

成员运行方式以终端为准；不承诺 `.sh` 可双击，也不通过改后缀或移除隔离标记绕过 macOS 安全检查。旧入口、独立 `frontend` 命令、`--frontend`、`--plain` 和数字菜单已移除。交互界面损坏时应重新下载；参数化 CLI、帮助和只读预演仍可使用。

## 组件与版本

| 组件标识 | 安装范围与默认值 |
| --- | --- |
| `jdk` | JDK 8，验证 `java`、`javac`、`jre` 并配置持久环境 |
| `gradle` | `4.5.1`、`6.8` 或 `all`；两版独立并存，默认 4.5.1 |
| `nvm` | nvm 0.40.8；Node `none\|10\|14\|18\|22\|all`，固定 10.24.1 / 14.21.3 / 18.20.8 / 22.23.3；默认选择并安装 14.21.3，`none` 仅配置 nvm |
| `iterm2` | iTerm2 3.7.3，macOS 13+，个人 Applications 目录 |
| `oh-my-zsh` | 固定框架及 git、z、zsh-autosuggestions、zsh-syntax-highlighting，保留用户主题与登录 Shell |
| `idea` | IDEA Community Open Source 2025.3.6.1 及全部六个推荐插件 |

安装页、一键安装全部及未指定 Node 版本的安装默认选择 Node 14.21.3。显式选择 `all` 才安装四版：首次或旧 default 失效时回退到 14，已有有效 default 保留（包括历史 Node 16）。单版安装把默认设为所选版，默认单版 14 同样遵循此规则；`none` 不下载 Node、不创建或改变 default。Node 16 不在新安装集合中，已有安装不自动删除。Node 10、14 使用 x64 包，Apple Silicon 需已有 Rosetta；Node 18、22 使用本机架构包。工具不自动安装 Rosetta 或回退源码编译。Oh My Zsh 需要可用 Git，缺少时预检阻止执行并提示处理，不自动安装系统开发工具。

两版 Gradle 同装保留有效默认，没有有效默认时用 4.5.1；单版安装将该版设为新终端默认。安装程序生成长期可加载的 `gradle_use`，版本切换无需重跑 helper。

```bash
# 仅当对应版本已经安装；自定义路径以本次结果为准
source "$HOME/.config/java-dev/env.sh"
gradle_use --list
gradle_use 6.8             # 只切换当前终端
gradle_use 6.8 --default   # 同时设置新终端默认

export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"
nvm ls
nvm use 22                # 只切换当前终端
nvm alias default 14      # 设置新终端默认
nvm use default           # 当前终端使用该默认
```

helper 和 TUI 是父终端的子进程；安装中验证配置不表示父终端已切换。实际成功版本、有效默认、加载路径和切换命令见结果与本次报告。[Gradle 指南](docs/environment/gradle.md)、[前端指南](docs/environment/frontend.md)说明详细规则。

## 参数化使用与 npx

```bash
bash devtool-helper.sh help
bash devtool-helper.sh help install
bash devtool-helper.sh --dry-run install --components all
bash devtool-helper.sh install --components jdk,gradle --gradle-version all --dry-run
bash devtool-helper.sh install --components nvm --node-version none
bash devtool-helper.sh uninstall --components nvm,iterm2,oh-my-zsh --dry-run
```

`help` 与动作前的全局 `--dry-run` 在本地完成，不联网；动作后的 `--help` / `--dry-run` 下载最新工具后显示业务帮助或只读计划。交互终端的组件参数预选到安装页，Enter 开始；无交互终端的实际安装必须明确 `--components`。卸载保留清单和确认，入口不会自动附加执行或免确认参数。

已有 Node >=14.14 / npm 的成员也可用 `npm-cli/` 本地打包的 `team-dev-env-preview`，只有 `install` / `uninstall` 动作。包保持 `private: true`，未公开发布，普通服务打包不生成 npm 包。用法见[前端指南](docs/environment/frontend.md#npm-打包与-npx-使用)和[npm 包说明](npm-cli/README.md)。

## 安装位置与记录

SDK 默认位于 `~/.local/share/java-dev/`；JDK 实际 Home 以验证结果为准。IDEA 和 iTerm2 位于当前 `$HOME/Applications`，如 `~/Applications/IntelliJ IDEA CE.app`、`~/Applications/iTerm.app`。工具不在主目录下重复添加 `Users/用户名`，不把应用自动装到系统 `/Applications`。nvm 默认 `~/.nvm`，Oh My Zsh 默认 `~/.oh-my-zsh`。

Java/Gradle 环境默认由 `~/.config/java-dev/{jdk,gradle}.sh`、`env.sh` 与 `gradle-default` 管理；nvm 使用实际 Shell profile 中的受管加载区块。工具保留用户内容，修改已有配置时保存相应首次备份；详细边界见[运行环境指南](docs/environment/runtime.md)。IDEA 2024 不再是新安装基线，已有应用不静默覆盖，先核对[卸载范围](docs/environment/cleanup.md)。

统一安装记录保存在 `~/Library/Logs/team-java-env/components/<本次记录>/`，包含计划、组件日志及阶段和最终状态。TUI 完整日志位于同一日志根的 `tui/`；卸载实际操作记录位于 `cleanup/`。维护者底层 `repair-env.sh` 仍保存 `history/` 中的报告、前后快照、配置差异及插件备份，见[修复历史指南](docs/repair-history.md)。预演不创建安装或清理记录。失败后查看真实阶段结果；文件复制、下载 100% 或版本命令通过不能代替整体完成。日志可能包含私有配置，分享前检查敏感内容。

## 维护者准备分发

Windows 和 macOS 服务端使用 Python 3.8+ 标准库，成员客户端只支持 macOS。首次部署先完成[Python 3 安装与验证](docs/service-startup.md#部署前安装-python-3)，然后在实际下载服务器的仓库根目录运行；Windows 将 `python3` 换成 `py -3`：

```bash
python3 server/manage.py start
```

也可使用 `server/start-server.command` / `server/start-server.cmd`。`start` 先绑定端口，再准备运行文件和软件资源、打包、启动服务；自动检测 IPv4，多候选时选择地址。运行文件有效则复用，否则根据 `resources/runtime-lock.json` 下载匹配的 GitHub Release 或镜像，服务器无需 Go/PyInstaller。源码变化后的运行文件构建与上传由维护者显式完成，见[运行文件发布指南](docs/environment/runtime-release.md)。

常规成员发布仅包含 `devtool-helper.sh`、`dev-env/team-dev-env.tar.gz`、`release.json` 三个文件。清单为 schema 2，以 `launcher` / `bundle` 保存路径、大小和摘要；不生成启动 ZIP、备用工具 ZIP 或旁置摘要。默认本地服务把软件资源只读映射到源资源库；需要拷到外部静态服务器时才加 `--with-resources`，部署副本不另写 `.sha256`。本机 `preview` 默认使用临时目录，退出清理，不覆盖正式发布目录。

`git pull` 不更新正在运行的服务或已有发布目录。停止自己管理的旧服务后重新 `start`，核对就绪输出和 HTTP `release.json` 的实际版本，再发送 `devtool-helper.sh?v=go-tui-…` 链接。端口占用时本次没有打包，旧地址可能仍提供旧版本。详细结构、退场文件、资源映射、启停和下载检查见[分发指南](docs/distribution.md)与[服务启动指南](docs/service-startup.md)。这些说明不代表新版运行文件已上传或团队服务已部署。

## 维护者底层命令行

公共组件入口不接受业务项目参数。以下底层命令保留项目修复、检查、构建及单项调试功能；在仓库根目录运行，下载仍要求正确的团队资源清单与摘要：

```bash
bash install_env.sh --project "/absolute/path/to/java-project" --dry-run
bash install_env.sh --project "/absolute/path/to/java-project"
bash dev-kit/.support/scripts/repair-env.sh --scope gradle --gradle-version 6.8
bash dev-kit/.support/scripts/check-env.sh --project "/absolute/path/to/java-project"
bash dev-kit/.support/scripts/runtime/verify-gradle.sh --project "/absolute/path/to/java-project"
bash dev-kit/.support/scripts/check-idea-project.sh --project "/absolute/path/to/java-project"
bash dev-kit/.support/scripts/runtime/config-idea-sdk.sh --project "/absolute/path/to/java-project"
bash dev-kit/.support/scripts/history.sh
bash dev-kit/.support/scripts/download-tools.sh --list
bash dev-kit/.support/scripts/download-tools.sh --id lombok
bash dev-kit/.support/scripts/services/mysql.sh up --dry-run
bash tools/uninstall-java-gradle.sh --components jdk,gradle --dry-run
```

`repair-env.sh --scope all|jdk|gradle|idea|plugins` 仍是 Java 修复范围，公共 `install --components all` 则是六组件全量。底层 `--gradle-version` 支持 `4.5.1|6.8`，默认 4.5.1。`--project` 明确指定真实 Java 项目后才执行构建；`SUCCEEDED` 或 `PROJECT_BUILD_VERIFIED_IDEA_PENDING` 不代替 IDEA GUI 同步。成员菜单不执行项目构建。

维护者源码卸载需要 Python 3.8+，非交互真删要求明确 `--components` 并加 `--apply --yes`；先只读预览并核对实例。来源不明的软件、用户内容及共享缓存保留，详见[卸载指南](docs/environment/cleanup.md)。可选 MySQL 需要 Docker 和相应环境变量；业务依赖缓存、JDBC 驱动、数据库服务及镜像不因安装包齐全而就绪。

## 主要文档

- [成员使用说明](dev-kit/使用说明.txt)
- [运行环境与版本切换](docs/environment/runtime.md)
- [独立 Gradle 与项目构建](docs/environment/gradle.md)
- [IDEA 与六个插件](docs/environment/ide.md)
- [前端环境与 npx](docs/environment/frontend.md)
- [Go TUI](docs/environment/tui.md)
- [资源准备](docs/resources/README.md)
- [修复历史](docs/repair-history.md)
- [验证记录与实机边界](docs/verification.md)
