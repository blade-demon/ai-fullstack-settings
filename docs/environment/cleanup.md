# 维护者实机测试前清理 JDK 与 Gradle

`tools/uninstall-java-gradle.sh` 用于在 macOS 测试电脑上卸载已发现的各版本 JDK、Gradle，并清理对应环境配置，便于重新测试安装流程。它需要 **Python 3.8+**，仅供维护者使用，不进入成员菜单或分发工具包。

默认只预览。脚本不会执行已安装的 Java/Gradle，也不会加载用户环境文件或 Shell 配置。先保存工作、退出使用这些 SDK 的程序，检查预览中的具体路径，再决定执行范围。

## 预览与执行

在仓库根目录运行：

```bash
# 默认预览；与 --dry-run 相同，不卸载、不改配置
bash tools/uninstall-java-gradle.sh

# 执行所选范围；显示计划后必须输入 DELETE 确认
bash tools/uninstall-java-gradle.sh --apply

# 完整重装测试：同时纳入系统 JDK 和 Gradle 用户缓存
bash tools/uninstall-java-gradle.sh --include-system --remove-caches --dry-run
bash tools/uninstall-java-gradle.sh --include-system --remove-caches --apply
```

`--apply --yes` 可省略输入确认，适合已经核对计划的自动化测试；`--yes` 必须与 `--apply` 搭配。预览不会创建清理备份。

发现系统 JDK 或 Homebrew JDK cask 时，未加 `--include-system` 会阻止整个 `--apply`，此时尚未修改文件或卸载软件。加上该参数重新预览并核对后，再执行清理；不要对整个脚本使用 `sudo`。

| 参数 | 用途 |
| --- | --- |
| `--dry-run` | 只展示安装、配置及待处理问题，默认行为 |
| `--apply` | 按计划执行；默认要求输入 `DELETE` |
| `--yes` | 与 `--apply` 搭配，省略输入确认 |
| `--include-system` | 纳入 `/Library/Java/JavaVirtualMachines` 中的安装和 Homebrew JDK cask；必要时仅针对具体系统安装目录使用 `sudo` |
| `--remove-caches` | 额外删除 `~/.gradle` 及可验证的自定义 `GRADLE_USER_HOME`；先备份用户配置 |
| `--jdk-dir /absolute/path` | 显式添加一个自定义 JDK 安装目录，可重复 |
| `--gradle-dir /absolute/path` | 显式添加一个自定义 Gradle 安装目录，可重复 |
| `--profile /absolute/path` | 添加需要检查的配置文件，可重复 |
| `--no-homebrew` | 明确跳过 Homebrew 的安装登记和卸载；若环境具体指向 Brew 安装目录，仍会阻止执行，避免绕过包管理器直接删除 |

自定义目录和配置示例：

```bash
bash tools/uninstall-java-gradle.sh \
  --jdk-dir "$HOME/SDKs/jdk-17" \
  --gradle-dir "$HOME/SDKs/gradle-8.14" \
  --profile "$HOME/.config/custom-java.sh" \
  --dry-run
```

## 自动处理范围

脚本扫描下列常见安装位置，识别各版本的具体目录；未知或无法可靠确认的目录会作为问题报告，不直接递归删除父目录。

- 本工具安装目录：`~/.local/share/java-dev/jdk*`、`~/.local/share/java-dev/gradle-*`，及覆盖的 `JDK_INSTALL_DIR`、`GRADLE_INSTALL_DIR`。
- 用户 JDK：`~/Library/Java/JavaVirtualMachines`、`~/.jdks`。
- 系统 JDK：`/Library/Java/JavaVirtualMachines`；执行清理需要 `--include-system`。
- SDKMAN 的 `candidates/java`、`candidates/gradle`：只删除具体版本目录及 `current`、本地安装链接，不跟随链接删除外部目标，也不删除其他 SDKMAN 工具。
- asdf、mise 的 Java/Gradle 安装目录。
- Homebrew 登记的 JDK/Gradle formula 和 JDK cask；cask 需要 `--include-system`，`--no-homebrew` 会跳过这一范围。
- `--jdk-dir`、`--gradle-dir` 显式指定且通过校验的额外安装。

默认保留 Gradle 用户缓存。`~/.gradle/wrapper/dists` 可能仍含各版本 Gradle 分发，因此要测试完整重新下载和安装，应加 `--remove-caches`。此参数会删除整个确认过的 Gradle 用户目录，包括依赖缓存；删除前保存 `gradle.properties`、`init.gradle`、`init.gradle.kts` 和 `init.d`。业务项目内的 `.gradle`、Wrapper 文件及构建配置不在清理范围内。

配置检查默认使用 `~/.config/java-dev/{env,jdk,gradle}.sh`；设置 `ENV_FILE` 后检查其所在目录的模块文件，以及 `ENV_FILE`、`JDK_ENV_FILE`、`GRADLE_ENV_FILE`、`SHELL_PROFILE` 显式指定的文件。还会检查 Bash/Zsh 常见启动文件、`ZDOTDIR` 下的 Zsh 配置及 `--profile` 添加的文件，移除本工具受管区块和可明确识别的 Java/Gradle 变量、加载入口与 PATH 条目，保留无关内容。

版本管理配置也会先备份再清理：`~/.tool-versions` 中的简单 `java`、`gradle` 选择行，以及 `~/.config/mise/config.toml` 的 `[tools]` 中使用简单字符串的 `java`、`gradle` 项。`MISE_CONFIG_DIR` 可覆盖 mise 配置目录；复杂的 Java/Gradle 配置需要先手工核对。

发现复杂配置、残留引用、未知安装目录或目录中混杂其他资料时，脚本会阻止执行并返回非零状态。根据提示核对文件、补充明确的目录或配置路径，再重新预览。不要把含糊的父目录作为安装目录传入。

Homebrew 安装通过其登记执行卸载，先处理 Gradle，再处理 JDK。formula 使用 `--force` 卸载所有已安装版本；不绕过依赖检查，也不使用 `--zap` 删除可能共享的文件。包管理器拒绝卸载时应处理其提示，不能直接删除 `Cellar` 或 `Caskroom` 来代替。参数含义见 [Homebrew 官方文档](https://docs.brew.sh/Manpage)。

## 备份与验证

执行前，配置文件和需保留的 Gradle 用户配置会备份到：

```text
~/Library/Logs/team-java-env/cleanup/<本次记录>/
├── files/       # 配置文件及 Gradle 用户配置备份
└── report.txt   # 本次计划、操作与结果
```

备份可能含私有仓库密码、令牌和其他个人设置；向他人提供报告或备份前先检查内容。SDK 安装和缓存本身不会完整备份，恢复 SDK 需要重新安装；不要整份恢复旧 Shell 配置来验证干净安装。

执行后查看报告，确认是否有失败或残留。**新开终端**后检查变量和命令路径，旧终端仍可能保留此前加载的变量：

```bash
printenv JAVA_HOME JAVA_8_HOME JRE_HOME GRADLE_HOME GRADLE_4_5_1_HOME GRADLE_USER_HOME
command -v java
command -v javac
command -v gradle
```

macOS 的 `/usr/bin/java`、`/usr/bin/javac` 是系统启动占位程序，清理后仍可能出现；脚本保留它们，不以这些路径存在判定 JDK 已安装，也不通过运行它们验证，以免弹出安装提示。随后按[运行环境指南](runtime.md)重新安装，并检查修复历史及实际项目构建结果。

## 需要手工核对的范围

脚本不会搜索全盘任意自定义目录。安装在其他位置的 JDK/Gradle 需通过显式目录参数添加；`--no-homebrew` 跳过的安装仍需另行处理。清理成功只表示本次所选、可确认的范围已处理，不代表跳过的 Homebrew 安装或未发现的目录也已清理。

以下内容保留并由维护者按实际情况核对：IDEA 内置 JBR、业务项目及其 `.gradle`/Wrapper、其他 SDKMAN 工具、全局 `/etc` 配置、`launchctl` 环境和 `.pkg` 安装收据。删除 JDK 文件不会自动保证这些外部登记和设置也已移除。
