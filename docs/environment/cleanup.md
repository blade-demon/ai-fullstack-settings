# 卸载 JDK、Gradle 与 IDEA

`tools/uninstall-java-gradle.sh` 用于在 macOS 测试电脑上删除能确认由本工具安装的 JDK、Gradle，并清理本工具的受管环境配置。交互运行时会询问是否同时删除检测到的 IDEA 软件；默认保留 IDEA 配置和用户插件。完整重装可显式加 `--include-idea`，同时删除应用、专属配置和用户插件。成员使用分发包中的独立「卸载环境.command」，它执行自带运行时的同一份卸载实现，无需预装 Python。维护者直接使用此源码入口时才需要 **Python 3.8+**；安装菜单不增加卸载选项。

本项目通过 tar 归档安装 JDK、ZIP 安装 Gradle、DMG 安装 IDEA。JDK/Gradle 的删除依据是安装根目录中的有效来源标记 `.team-java-env-install.json`：`schema` 为 `1`、`tool` 为 `team-java-env`、`kind` 分别为 `jdk` 或 `gradle`，并且目录结构通过相应 SDK 校验。IDEA 应用继续按静态应用标识识别。

只有今后本工具新下载、校验并发布的 SDK 才写入来源标记。复用已有或外部 SDK 时不添加标记；旧版安装即使位于默认 `~/.local/share/java-dev` 下，只要没有有效标记也会保留。目录名、版本号、`JAVA_HOME` 或其他环境引用都不能代替来源证明。

真实交互终端默认进入清理引导；非交互默认和显式 `--dry-run` 只预览。脚本不执行已安装的 Java/Gradle/IDEA 二进制，也不加载用户环境文件或 Shell 配置。先保存工作，核对展示的路径和范围；最终输入 `DELETE` 确认后，才请求正常退出所选 IDEA。若有未保存内容、用户取消退出、系统拒绝自动化请求或退出超时，会停止全部清理并保留软件，提示手动退出后重试；不会强制结束 IDEA。

**清理工具直接删除或清理所选内容，不备份 JDK/Gradle 配置、IDEA 应用、配置或插件，也不自动回滚。** 外部 SDK、原有 Shell 变量与 PATH 引用、用户的版本管理选择以及 Gradle 用户配置和缓存都会保留。

## 成员双击卸载

从新版 `start.zip` 解压后，双击「卸载环境.command」：入口会下载并校验最新工具，打开 Go TUI 安全卸载页面。选择只读预览，或进入保留原 DELETE 确认的清理引导；卸载页不会启动 SDK 运行探测。完整工具 ZIP 中也包含同名入口，可直接双击；须保留同目录的隐藏 `.support`。

先保存工作，再按提示选择是否删除 IDEA 软件、核对完整删除清单，输入 `DELETE` 后才执行。默认保留 IDEA 配置和用户插件；取消不执行删除。Go TUI 会恢复结果页；普通模式的结果留在终端窗口，按回车后关闭。业务项目、外部 SDK 和 Gradle 用户配置及缓存继续保留；无来源标记的旧安装不会仅凭目录名删除。

两个 Gradle 版本（4.5.1、6.8）均按来源标记识别，不需要分别下载卸载工具。每次卸载只保存操作记录，不建立软件或配置备份，具体边界见下文。

在完整工具目录中，仅预览可执行：

```bash
bash 卸载环境.command --dry-run
```

已有用户要重新下载一次 `start.zip` 才能获得新入口；服务器地址不变时，每次启动都会获取最新发布工具。已下载并解压的完整工具包是快照，更新需重新下载。若提示卸载工具缺失、校验失败或清单无效，重新下载完整工具，不要单独移动或替换内部可执行文件。

## 维护者构建成员卸载工具

唯一源码为 `tools/uninstall_java_gradle.py`；用 macOS **python.org Python 3.14.6 universal2** 和固定 `PyInstaller==6.22.3` 构建包含 arm64 / x86_64 的单文件程序。成员无需 PyInstaller 或 Python，Windows 下载服务器也不需要安装 PyInstaller。仅有 arm64 的 Python 不能用于这个双架构构建。

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

把三个文件一起交给实际下载服务器，保留该相对目录；随后使用原来的 `server/manage.py start` 或 `package` 发布。它们是生成产物，不通过 Git 分发，也不在 `resources/catalog.tsv` 的软件下载清单中。服务端会核对产物摘要、源码摘要及双架构，不会在 Windows 上运行 Mac 工具。

`source_sha256` 使用 UTF-8（忽略 BOM）、统一 LF 换行后的源码，避免 Windows 的 CRLF 导致错误判为过期。修改卸载源码后须重新构建；缺失、损坏或源码摘要不符时，打包会停止并提示处理，不会发布一个无法使用的卸载入口。成员执行前还会核对包内可执行文件摘要。

构建采用 PyInstaller 的本地签名处理，不代表已取得 Developer ID 签名或 Apple 公证；首开及企业设备策略仍需遵循团队的 macOS 分发规则。[PyInstaller 打包说明](https://pyinstaller.org/en/stable/operating-mode.html)

## 维护者源码预览与执行

在仓库根目录运行：

```bash
# 在交互终端中进入引导，选择是否删除 IDEA，再核对并确认完整计划
bash tools/uninstall-java-gradle.sh

# 只预览；不询问、不退出 IDEA、不卸载或改配置
bash tools/uninstall-java-gradle.sh --dry-run

# 执行所选范围；显示计划后必须输入 DELETE 确认
bash tools/uninstall-java-gradle.sh --apply

# 只删除 IDEA 软件，保留用户配置和插件
bash tools/uninstall-java-gradle.sh --include-idea-apps --apply

# 纳入带有效来源标记的系统 JDK；Gradle 用户配置和缓存仍保留
bash tools/uninstall-java-gradle.sh --include-system --dry-run
bash tools/uninstall-java-gradle.sh --include-system --apply

# 同时预览并清理 IDEA 全版本应用、专属配置和插件
bash tools/uninstall-java-gradle.sh --include-idea --dry-run
bash tools/uninstall-java-gradle.sh --include-idea --apply

# 同时纳入系统 IDEA、IDEA 缓存/Local History/日志
bash tools/uninstall-java-gradle.sh --include-idea --include-system --remove-caches --dry-run
bash tools/uninstall-java-gradle.sh --include-idea --include-system --remove-caches --apply
```

交互引导中的“是否删除 IDEA”用于选择范围；输入 `DELETE` 是对完整永久清理计划的最终确认。回答否、留空或取消 IDEA 选择时，会明确提示保留 IDEA。最终确认之前不关闭应用，也不删除文件。退出应用后重新扫描并校验，避免 IDEA 保存配置使旧计划失效。

`--apply --yes` 可省略输入确认，适合已经核对计划的自动化测试；`--yes` 必须与 `--apply` 搭配。非交互执行须显式指定删除范围；预览不修改文件、不退出 IDEA，也不创建操作记录。

发现计划删除的带有效来源标记的系统 JDK，或 `/Applications` 中的 IDEA 时，未加 `--include-system` 会阻止清理，且不会请求退出 IDEA。IDEA 在交互选择后或显式使用 `--include-idea-apps` / `--include-idea` 时纳入计划。加上所需参数重新预览并核对后，再执行清理；不要对整个脚本使用 `sudo`。

| 参数 | 用途 |
| --- | --- |
| `--dry-run` | 只展示安装、配置及待处理问题；不询问、不退出应用；非交互默认行为 |
| `--apply` | 按计划执行；默认要求输入 `DELETE` |
| `--yes` | 与 `--apply` 搭配，省略输入确认 |
| `--include-system` | 允许清理带有效来源标记的系统 JDK；开启 IDEA 清理时也允许 `/Applications` 中的 IDEA；必要时仅针对具体系统安装目录使用 `sudo` |
| `--include-idea-apps` | 额外删除可识别的 IDEA 软件，保留配置、用户插件和缓存 |
| `--include-idea` | 额外删除可识别版本的 IDEA 应用、专属配置及用户插件 |
| `--remove-caches` | 仅在同时指定 `--include-idea` 时额外删除 IDEA 缓存、Local History 和日志；不删除 Gradle 用户配置或缓存 |
| `--jdk-dir /absolute/path` | 补充一个自定义 JDK 候选安装目录，可重复；仍须有效来源标记，不强制删除外部 SDK |
| `--gradle-dir /absolute/path` | 补充一个自定义 Gradle 候选安装目录，可重复；仍须有效来源标记，不强制删除外部 SDK |
| `--idea-app /absolute/path/App.app` | 显式添加一个自定义 IDEA 应用，可重复；须同时指定 `--include-idea-apps` 或 `--include-idea` |
| `--idea-plugins-dir /absolute/path` | 显式添加一个专用 IDEA 用户插件目录，可重复；须同时指定 `--include-idea` |
| `--profile /absolute/path` | 添加需要检查的配置文件，可重复 |

自定义目录和配置示例：

```bash
bash tools/uninstall-java-gradle.sh \
  --jdk-dir "$HOME/SDKs/jdk-17" \
  --gradle-dir "$HOME/SDKs/gradle-8.14" \
  --profile "$HOME/.config/custom-java.sh" \
  --dry-run

# Toolbox 或其他自定义安装位置须提供具体 .app，不能传宽泛父目录
bash tools/uninstall-java-gradle.sh \
  --include-idea \
  --idea-app "$HOME/Tools/IntelliJ IDEA.app" \
  --idea-plugins-dir "$HOME/IDEA-plugins" \
  --dry-run
```

## 自动处理范围

脚本在下列常见位置查找候选安装，只删除带有效来源标记且结构校验通过的 JDK/Gradle；外部或来源不明的安装保留，不直接递归删除父目录。

- 本工具安装目录：`~/.local/share/java-dev/jdk*`、`~/.local/share/java-dev/gradle-*`，及覆盖的 `JDK_INSTALL_DIR`、`GRADLE_INSTALL_DIR`。
- 用户 JDK：`~/Library/Java/JavaVirtualMachines`、`~/.jdks`。
- 系统 JDK：`/Library/Java/JavaVirtualMachines`；只有带有效来源标记的安装才纳入删除，执行需要 `--include-system`。
- SDKMAN 的 `candidates/java`、`candidates/gradle`：外部版本、`current` 和本地安装链接保留，也不删除其他 SDKMAN 工具。
- asdf、mise 的 Java/Gradle 安装目录。
- `--jdk-dir`、`--gradle-dir` 显式指定的额外候选安装；这两个参数不绕过来源标记。

JDK/Gradle 的符号链接及含链接祖先的安装路径不会删除。IDEA 下载 JDK 时生成的 `.<jdk名称>.intellij` JSON 辅助元数据只读识别并保留，不把它当作 JDK 安装或来源标记。

Gradle 用户配置和缓存可能由外部版本共用，因此本次全部保留，包括 `~/.gradle`、自定义 `GRADLE_USER_HOME`、Wrapper 分发、依赖缓存、`gradle.properties`、`init.gradle`、`init.gradle.kts` 和 `init.d`。`--remove-caches` 也不会删除这些内容。业务项目内的 `.gradle`、Wrapper 文件及构建配置不在清理范围内。

开启 `--include-idea` 后，额外处理下列范围：

- `~/Applications` 和 `/Applications` 中的具体 IDEA `.app`：静态读取 `Contents/Info.plist`，按 `com.jetbrains.intellij` 或 `com.jetbrains.intellij.ce` 标识识别，包含应用内置 JBR 和插件；系统目录执行清理需要 `--include-system`。
- `~/Library/Application Support/JetBrains/{IdeaIC,IntelliJIdea,IntelliJ}<版本>` 中可明确识别的版本专属目录，包含用户配置和 `plugins`；旧版 `~/Library/Preferences/<产品><版本>` 配置和 `~/Library/Application Support/<产品><版本>` 插件也会清理。
- `~/Library/Preferences/com.jetbrains.intellij.plist` 和 `com.jetbrains.intellij.ce.plist` 两份 IDEA 专属偏好文件，以及隐藏旧版 `~/.<产品><版本>` 下的 `config`、`plugins` 子目录。产品名和版本须完整匹配；不删除整个 JetBrains 父目录、隐藏旧版父目录或其他 JetBrains 产品。
- `--idea-app`、`--idea-plugins-dir` 显式指定且通过校验的具体应用或专用插件目录；开启 IDEA 清理时，`IDEA_APP`、`IDEA_PLUGINS_DIR` 指定的位置也会纳入。

默认保留 IDEA 缓存和日志；同时指定 `--include-idea --remove-caches` 才删除对应的 `~/Library/Caches/JetBrains` 和 `~/Library/Logs/JetBrains` 版本专属目录、旧版 `~/Library/Caches/<产品><版本>` 和 `~/Library/Logs/<产品><版本>`，以及隐藏旧版 `~/.<产品><版本>/system`。缓存目录包含 **Local History**，因此此参数也会永久删除本地历史。现代 macOS 默认目录与用户插件的位置依据 [JetBrains 官方目录说明](https://www.jetbrains.com/help/idea/directories-used-by-the-ide-to-store-settings-caches-plugins-and-logs.html)。

配置检查默认使用 `~/.config/java-dev/{env,jdk,gradle}.sh`；设置 `ENV_FILE` 后检查其所在目录的模块文件，以及 `ENV_FILE`、`JDK_ENV_FILE`、`GRADLE_ENV_FILE`、`SHELL_PROFILE` 显式指定的文件。还会检查 Bash/Zsh 常见启动文件、`ZDOTDIR` 下的 Zsh 配置及 `--profile` 添加的文件，清除本工具受管配置及对应待删除 SDK 的设置，保留外部 SDK 的原有变量与 PATH 引用。共享 Shell 文件即使在受管标记内混入了别名、编辑器变量等无关内容，也会逐行保留；混合逻辑无法安全拆分时阻止执行。专属环境文件清理后为空时直接删除；共享的 Shell 启动文件始终保留，即使其路径同时被指定为 `ENV_FILE`。引用仍保留的环境或共享配置文件的加载行也会保留，以便其中的无关设置继续生效。

清理后位于文件末尾、下面仅有空行的孤立 `# Java 开发环境` 标题会删除；标题下面仍有保留设置或其他内容时原样保留，不删除其他注释。

旧 `env.sh` 中相邻的静态 `JAVA_HOME` 赋值与完整已知的 `_java_dev_prefer_jdk` 函数定义、调用及 `unset` 序列会精确识别并清除。函数被改写或夹带其他命令时保持阻断，原文件不修改；不能仅凭函数名删除任意代码。

旧配置备份仅检查默认的 `~/.config/java-dev/env.sh.bak`，大小不超过 64 KiB、为普通文件，且完整内容只能由已知工具注释、单一静态 `JAVA_HOME` 赋值及完整旧函数定义/调用/`unset` 序列组成时才删除。包含用户设置、额外命令、改写函数或无法完整确认的备份保留；不按 `.bak` 扩展名删除任意文件，也不通过备份内容认领旧 SDK。引用这份备份的加载入口仅在备份已确认删除时清理。

仅对 `~/.config/java-dev` 和 `~/.local/share/java-dev` 两个工具目录检查清理后的空目录状态：预览会显示“清理后为空才删除目录”，执行时仅使用 `rmdir` 删除空目录，保留链接、含链接祖先的路径和所有非空目录。原有无来源标记的 `gradle-4.5.1` 若仍在安装目录下，该 `java-dev` 目录会继续保留。

`~/.tool-versions`、asdf、mise 等用户的 Java/Gradle 版本选择配置保留，不因本工具 SDK 清理而删除其他版本的选择。

来源标记无效或来源不明的 SDK 保留。发现无法安全拆分的本工具相关配置，或已认领的待删除目录校验失败、混杂其他资料时，脚本会阻止执行并返回非零状态。根据提示核对文件，再重新预览。外部 SDK 的引用会保留，不作为必须删除的残留；不要把含糊的父目录作为安装目录传入。

## 操作记录与验证

执行时只保存计划和执行结果：

```text
~/Library/Logs/team-java-env/cleanup/<本次记录>/
└── report.txt   # 本次计划、操作与结果，不含配置文件正文
```

本次清理不创建 `files/` 备份目录或 `.bak`，也不自动回滚。需要恢复安装时须重新安装，已删除的配置、插件和缓存不能通过本次操作记录恢复。旧清理记录目录中的历史 `files/` 备份和报告继续保留；仅上述严格识别的旧 `env.sh.bak` 可纳入删除。安装/修复流程自身的备份行为不受此清理工具变更影响。

执行后查看报告，确认是否有失败或残留。**新开终端**后检查变量和命令路径，旧终端仍可能保留此前加载的变量：

```bash
printenv JAVA_HOME JAVA_8_HOME JRE_HOME GRADLE_HOME GRADLE_4_5_1_HOME GRADLE_6_8_HOME GRADLE_USER_HOME
command -v java
command -v javac
command -v gradle
```

macOS 的 `/usr/bin/java`、`/usr/bin/javac` 是系统启动占位程序，清理后仍可能出现；脚本保留它们，不以这些路径存在判定 JDK 已安装，也不通过运行它们验证，以免弹出安装提示。随后按[运行环境指南](runtime.md)重新安装，并检查修复历史及实际项目构建结果。

## 需要手工核对的范围

脚本不会搜索全盘任意自定义目录，也不遍历整个 Toolbox 目录。安装在其他位置的本工具 JDK/Gradle 可通过显式目录参数补充查找，仍须有效来源标记；其他位置的 IDEA 须通过 `--idea-app` 指定具体 `.app`，自定义用户插件目录通过 `--idea-plugins-dir` 添加。IDEA 自定义的配置、缓存和日志路径需另行核对。清理成功只表示本次所选、可确认的范围已处理，不代表外部 SDK 或未发现的目录也已删除。

以下内容保留并由维护者按实际情况核对：业务项目及其 `.idea`/`.gradle`/Wrapper、其他 JetBrains 产品、其他 SDKMAN 工具、全局 `/etc` 配置、`launchctl` 环境和 `.pkg` 安装收据。未开启 `--include-idea` 时保留 IDEA 应用、配置、插件及内置 JBR；开启后内置 JBR 随所选应用删除。删除安装文件不会自动保证这些外部登记和设置也已移除。
