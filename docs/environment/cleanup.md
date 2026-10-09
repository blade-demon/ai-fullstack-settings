# 六组件安全卸载

成员运行 **`bash devtool-helper.sh uninstall`**，同一入口提供 JDK、Gradle、nvm/Node、IDEA、iTerm2、Oh My Zsh 的组件及实例选择。无需 Python，包内 universal2 运行时执行同一卸载实现。维护者源码入口 `tools/uninstall-java-gradle.sh` 保留旧名字，需要 Python 3.8+；名字不代表只支持 Java。

## 成员选择、预览与确认

卸载页默认全部不选，方向键移动、空格选组件，进入实例页后选择具体可删除对象。页面列出来源、路径、配置影响、用户内容保留和阻断原因；Enter 进入最终清单，输入 `DELETE` 才执行。空选择不删除，没有一键全卸载。TUI/helper/npm 不自动添加 --apply/--yes，不自动提权。

扫描只读、静态检查文件与收据，不运行已安装 Java/Gradle/Node/IDEA 或加载用户 Shell 文件。组件范围在扫描、计划、配置修改和删除前过滤；只选 jdk 不删 gradle/idea，只选某一版本或应用不附带清理其他实例。实例 ID 绑定路径、对象身份、来源和应用标识，确认后重扫发现替换或变化会拒绝原选择，不扩大范围。

IDEA 组件选择可保留用户配置、SDK 登记和用户插件，公共所选组件的保留提示默认为保留；需要清理时明确选择并核对具体关联。最终确认后才请求所选 IDEA 正常退出；未保存内容、拒绝退出、超时等会停止清理，不强制杀进程。iTerm2 不自动退出，正在运行或作为当前终端宿主时需从其他终端重试。

**清理永久删除所选范围，不建立软件或配置备份，不自动回滚。** 实际操作记录不能恢复软件、插件或用户数据；请先查看只读计划。已有安装/修复备份和历史保留，不因迁移删除。

```bash
bash devtool-helper.sh uninstall --components jdk,gradle --dry-run
bash devtool-helper.sh uninstall --components nvm,iterm2,oh-my-zsh --dry-run
bash devtool-helper.sh uninstall --components idea --include-idea-apps --dry-run
```

无交互终端默认只预览，真删要求明确 --components 并同时指定 --apply --yes；否则返回用法错误，不把默认预览提升成全量删除。help/global 启动器预演无需联网，动作后 --dry-run 下载工具再显示业务清单。

## 来源与组件边界

| 组件 | 可确认对象与清理边界 |
| --- | --- |
| JDK | 有效 `.team-java-env-install.json` 且 SDK 结构通过校验；外部或无标记旧安装保留，不按 JAVA_HOME/目录名认领 |
| Gradle | 独立受管版本按标记识别；只清所选版本、登记及默认引用；其他版本、JDK、用户缓存保留 |
| nvm/Node | 管理器与每个 Node 分别认领；可信来源快照下处理受管对象，外部版本、用户别名和未知内容保留 |
| IDEA | 静态读取具体应用标识及 product-info/版本选择器；仅清理与所选应用明确关联且不共享的数据，应用内 JBR 不是独立 JDK 候选 |
| iTerm2 | 可信外置收据绑定绝对路径、Bundle ID、版本、CDHash、Info.plist/执行文件摘要；不足证据或替换应用保留 |
| Oh My Zsh | 框架与外部插件分别认领，快照检查新增/修改内容；保留用户主题、外置 ZSH_CUSTOM、系统 zsh/Git/CLT |

JDK/Gradle 标记 schema=1、tool=team-java-env、kind 为 jdk/gradle；只在本工具新下载、校验并发布安装时写入，复用外部 SDK 不补标记。受管安装符号链接及链接祖先不授权删除；宽泛用户父目录不能因一个标记变成可删范围。删目录前重新检查整个目录树及身份，新增嵌套文件、修改或来源变化会阻止执行。

Gradle 当前模块登记、gradle_use 与 `GRADLE_DEFAULT_FILE` 按具体版本处理；最后一版清理仅移除生成函数及默认加载，受管区块里的用户设置仍保留。默认路径从明确环境及模块静态读取，不执行配置。默认引用失效不自动改为另一个版本，保留版本可新开终端加载后用 gradle_use --list 核对并显式设置。`~/.gradle`、GRADLE_USER_HOME、Wrapper/业务依赖缓存、gradle.properties、init 脚本及业务项目 .gradle/Wrapper 永久不在本工具删除范围。

受管 Node 的全局 npm 包随对应版本删除，具体影响列在计划；历史 Node 16 等发现不受新安装白名单限制，只有明确选中相应实例才处理。用户别名/外部 Node/未知内容存在时保留 nvm 管理器和加载配置；静态跟踪 alias 链，只清理失效且受管的 default。nvm、框架和插件的 files/links/directories 来源快照用于判断用户修改，不完整证据保留对象。

nvm/Oh My Zsh 加载区块按来源记录中的实际 profile 清理，支持 Bash、Zsh、ZDOTDIR、自定义 SHELL_PROFILE/NVM_DIR/ZSH，包括带引号路径。框架保留而受管插件删除时，同步清理生成插件列表，保留框架可继续加载；不删除用户配置文件或未知配置。

iTerm2 保留偏好、历史及会话；最终确认后复核签名，运行中阻止删除，不为了卸载自动关闭当前终端。IDEA 默认保留缓存、日志和 Local History；--remove-caches 只有明确纳入 IDEA 配置清理才处理相应版本目录，会永久删除 Local History，不影响 Gradle 缓存。其他 IDEA 版本、共享/关联不明配置及其他 JetBrains 产品保留。

## 维护者构建成员卸载工具

正常部署不需要下载服务器执行本节构建。Windows 或 macOS 拉取仓库后继续运行原 `start`，会复用有效的界面与卸载产物，或按 `resources/runtime-lock.json` 从 GitHub Release / 镜像自动下载匹配运行文件。首次缺少运行文件需联网，缓存有效时可离线使用；服务器无需手动搬运 ZIP。

本节供修改卸载实现的维护者使用。唯一源码为 `tools/uninstall_java_gradle.py`；用 macOS **python.org Python 3.14.6 universal2** 和固定 `PyInstaller==6.22.3` 构建包含 arm64 / x86_64 的单文件程序。成员无需 PyInstaller 或 Python，Windows 下载服务器也不需要安装 PyInstaller。仅有 arm64 的 Python 不能用于这个双架构构建。

以下示例使用 python.org Python 3.14.6 的安装路径；若安装在其他位置，替换第一行的解释器路径。构建器要求这两个固定版本及虚拟环境，附带许可材料与所选运行时一致。在仓库根目录执行，构建依赖放入临时虚拟环境，不修改系统 Python：

```bash
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14 -m venv /tmp/team-cleanup-build
/tmp/team-cleanup-build/bin/python -m pip install 'pyinstaller==6.22.3'
/tmp/team-cleanup-build/bin/python tools/build-cleanup.py
python3 tools/build-cleanup.py --verify-only
```

默认生成：

```text
resources/cleanup/
├── cleanup-macos-universal2
├── manifest.json
└── THIRD_PARTY_NOTICES.txt
```

维护者确认 Go TUI 产物也与当前源码匹配后，运行 `tools/release-runtimes.py` 生成包含两套运行文件的 ZIP 与锁，上传匹配的 GitHub Release，并将 `resources/runtime-lock.json` 随源码提交；详见[运行文件发布步骤](runtime-release.md)。目前没有 CI 自动构建或上传。二进制是生成产物，不直接通过 Git 分发，也不在 `resources/catalog.tsv` 的 25 项软件下载清单中；Git 保存的是下载地址、摘要、大小及源码摘要的锁。服务器会核对这些信息及双架构，不会在 Windows 上运行 Mac 工具。

`source_sha256` 使用 UTF-8（忽略 BOM）、统一 LF 换行后的源码，避免 Windows 的 CRLF 导致错误判为过期。修改卸载源码后须重新构建并更新对应发布锁。`start` 或 `prepare-runtimes` 可自动补齐失效缓存；`prepare-runtimes --offline` 只读校验，不联网或写入。`package` 仍只使用本地产物，缺失、损坏或源码摘要不符时停止，不会联网或发布无法使用的卸载入口。成员执行前还会核对包内可执行文件摘要。

离线部署可选择把已校验的 `resources/tui/` 和 `resources/cleanup/` 七个文件按原目录一起复制到服务器，再运行 `prepare-runtimes --offline`；这不是联网部署的必需步骤。

构建采用 PyInstaller 的本地签名处理，不代表已取得 Developer ID 签名或 Apple 公证；首开及企业设备策略仍需遵循团队的 macOS 分发规则。[PyInstaller 打包说明](https://pyinstaller.org/en/stable/operating-mode.html)

## 维护者源码计划与执行

公共组件与实例参数也可用于源码入口；在仓库根目录运行：

```bash
# 只读计划；不退出应用或创建操作记录
bash tools/uninstall-java-gradle.sh --components jdk,gradle --dry-run
bash tools/uninstall-java-gradle.sh --components nvm,iterm2,oh-my-zsh --dry-run
bash tools/uninstall-java-gradle.sh --components all --plan-json

# 用上次计划中的真实实例 ID 选择，不使用示例 ID 执行
bash tools/uninstall-java-gradle.sh --components gradle --instances 'gradle:实际ID' --dry-run

# 交互执行有清单及 DELETE
bash tools/uninstall-java-gradle.sh --components jdk,gradle --apply
bash tools/uninstall-java-gradle.sh --components idea --include-idea-apps --apply
bash tools/uninstall-java-gradle.sh --components idea --include-idea --remove-caches --dry-run

# 已核对范围的隔离自动化才显式使用此免输入方式
bash tools/uninstall-java-gradle.sh --components jdk,gradle --apply --yes
```

--plan-json 是只读 **schema 1** 实例计划（与成员发布 release.json 的 schema 2 用途不同），包含 id/component/path/label/removable/reason、selected 和删除/配置/说明/阻断项。--instances 是排他白名单，必须明确 --components，未知、跨组件、不可删或来源变化的 ID 拒绝，不因重扫增加实例。

| 参数 | 用途 |
| --- | --- |
| --components CSV\|all | 仅扫描选择的六类组件；all 必须单独使用 |
| --instances CSV | 仅处理列出的有效实例 ID，不能扩大组件范围 |
| --dry-run / --plan-json | 只读清单/JSON，不询问、不退出应用、不修改 |
| --apply / --yes | 执行并输入 DELETE；--yes 只能与 --apply 及明确组件范围配合 |
| --include-system | 纳入有有效来源标记的系统 JDK/系统 IDEA；不对整个脚本使用 sudo |
| --include-idea-apps | 删除所选 IDEA 应用，保留用户配置、SDK 登记及插件 |
| --include-idea | 纳入与所选应用明确关联且不共享的配置及插件 |
| --remove-caches | IDEA 配置清理时额外处理其缓存/Local History/日志 |
| --jdk-dir / --gradle-dir | 添加具体候选绝对路径，可重复，不绕过来源验证 |
| --idea-app / --idea-plugins-dir | 具体自定义应用/专用插件目录，可重复，需相应 IDEA 标志 |
| --profile | 添加待检查配置文件，可重复 |

系统范围缺少 include-system 会阻止执行；工具不自动提权。IDEA 应用内 JBR 随应用删除，不能选作独立 JDK。自定义 Toolbox 位置需具体 .app，不传宽泛父目录。

旧维护者无组件交互引导仍兼容原 Java 范围：默认 JDK/Gradle，先询问是否删 IDEA，选删除后的保留提示默认不保留。它与新版明确组件选择的默认不同，始终以实际提示和最终 DELETE 清单为准。非交互无组件默认只读扫描全候选，不能加 apply/yes 将其提升为真删。

## 受管 Java 配置与历史兼容

配置检查默认使用 `~/.config/java-dev/{env,jdk,gradle}.sh`；设置 `ENV_FILE` 后检查其所在目录的模块文件，以及 `ENV_FILE`、`JDK_ENV_FILE`、`GRADLE_ENV_FILE`、`SHELL_PROFILE` 显式指定的文件。还会检查 Bash/Zsh 常见启动文件、`ZDOTDIR` 下的 Zsh 配置及 `--profile` 添加的文件，按所选组件及实例清除相应受管配置及待删除 SDK 的设置，保留外部 SDK 的原有变量与 PATH 引用。共享 Shell 文件即使在受管标记内混入了别名、编辑器变量等无关内容，也会逐行保留；混合逻辑无法安全拆分时阻止执行。专属环境文件清理后为空时直接删除；共享的 Shell 启动文件始终保留，即使其路径同时被指定为 `ENV_FILE`。引用仍保留的环境或共享配置文件的加载行也会保留，以便其中的无关设置继续生效。

清理后位于文件末尾、下面仅有空行的孤立 `# Java 开发环境` 标题会删除；标题下面仍有保留设置或其他内容时原样保留，不删除其他注释。

旧 `env.sh` 中相邻的静态 `JAVA_HOME` 赋值与完整已知的 `_java_dev_prefer_jdk` 函数定义、调用及 `unset` 序列会精确识别并清除。函数被改写或夹带其他命令时保持阻断，原文件不修改；不能仅凭函数名删除任意代码。

旧配置备份仅检查默认的 `~/.config/java-dev/env.sh.bak`，大小不超过 64 KiB、为普通文件，且完整内容只能由已知工具注释、单一静态 `JAVA_HOME` 赋值及完整旧函数定义/调用/`unset` 序列组成时才删除。包含用户设置、额外命令、改写函数或无法完整确认的备份保留；不按 `.bak` 扩展名删除任意文件，也不通过备份内容认领旧 SDK。引用这份备份的加载入口仅在备份已确认删除时清理。

仅对 `~/.config/java-dev` 和 `~/.local/share/java-dev` 两个工具目录检查清理后的空目录状态：预览会显示“清理后为空才删除目录”，执行时仅使用 `rmdir` 删除空目录，保留链接、含链接祖先的路径和所有非空目录。原有无来源标记的 `gradle-4.5.1` 若仍在安装目录下，该 `java-dev` 目录会继续保留。

`~/.tool-versions`、asdf、mise 等用户的 Java/Gradle 版本选择配置保留，不因本工具 SDK 清理而删除其他版本的选择。

来源标记无效或来源不明的 SDK 保留。发现无法安全拆分的本工具相关配置，或已认领的待删除目录校验失败、混杂其他资料时，脚本会阻止执行并返回非零状态。根据提示核对文件，再重新预览。外部 SDK 的引用会保留，不作为必须删除的残留；不要把含糊的父目录作为安装目录传入。

## 记录与卸载后加载

实际执行只保存计划、操作和结果到：

```text
~/Library/Logs/team-java-env/cleanup/<本次记录>/report.txt
```

确认前取消或没有清理内容不生成记录；不创建 files/ 备份或新的 .bak，旧历史保留。完成后查看失败及保留项，**新开终端**核对命令路径及剩余版本；旧终端可能仍持有已加载的变量/函数。

```bash
printenv JAVA_HOME GRADLE_HOME GRADLE_4_5_1_HOME GRADLE_6_8_HOME NVM_DIR
command -v gradle
command -v node
# 保留 Gradle 时加载实际 env.sh 并查看登记
gradle_use --list
# 保留 nvm 时加载实际 nvm.sh 再看版本
nvm ls
```

macOS /usr/bin/java、javac 是系统占位程序，保留且不运行它们检查，避免触发系统安装提示。剩余版本有有效配置时可继续切换，不要求重装全部环境。

不会全盘搜索任意路径，也不清业务项目 .idea/.gradle/Wrapper、其他 SDKMAN 工具、用户版本选择、/etc、launchctl 环境或 .pkg 收据。未发现的自定义目录及 IDEA 自定义缓存需维护者另行核对；清理成功只表示本次明确选择且可确认的范围已处理。
