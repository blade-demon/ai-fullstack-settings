# JDK、Gradle 与完整环境配置

本工具面向 macOS，一键全量包含六组件，Java 基线为 **JDK 8、独立 Gradle 4.5.1、IDEA 2025.3.6.1 与六个插件**；Gradle 可选 6.8 或两版同装。SDK 安装在用户目录，不使用 `sudo`。本仓库是环境工具，不是 Java 业务项目。

## 成员修复流程

运行 `bash devtool-helper.sh`，选择安装与配置，在同一页勾选 jdk、gradle 等组件，左右键选择版本，Enter 直接预检并执行。首页一键安装全部包含 JDK、Gradle、nvm/Node、iTerm2、Oh My Zsh、IDEA/插件，按此顺序运行；Gradle 自动补入并去重 JDK 8 依赖。仅选 IDEA 不隐式安装 JDK。

安装页明确展示所选版本、目标和默认值影响；预检失败不执行并保留选择，空选择不安装。默认 Gradle 4.5.1，选择 all 安装两版并保留有效默认，无有效默认时用 4.5.1；单版设为默认。成员流程不选择项目、不执行构建，结果中的版本/环境验证不能替代业务验收。

项目检查、构建、仅下载、历史和 MySQL 保留为维护者底层命令行，公共组件入口不接受 --project/--scope。细节见[Gradle 指南](gradle.md)、[IDE 指南](ide.md)和[前端指南](frontend.md)。

## 环境预检

扫描同时关注安装状态和持久化配置：JDK 是否为完整 1.8、独立 Gradle 是否为所选目标版本（默认 4.5.1）、IDEA 是否为团队版本，以及受管环境和 Shell 入口是否完整。维护者通过 `check-env.sh --project` 指定项目时，还会只读检查 IDEA 的 Project SDK、Gradle JVM 和分发设置；待配置时返回 `1` 并打印实际路径及设置入口。扫描不会开始安装或业务构建；静态检查不能替代实际版本验证、终端构建或 IDEA 同步。

JDK 探测依次考虑已生成环境文件中的 `JAVA_HOME`、当前环境的 `JAVA_HOME`、`JDK_INSTALL_DIR`；`JDK_AUTO_DETECT=true` 时还检查系统登记与可识别的 PATH JDK。只有 `java`、`javac` 都符合 1.8 才采用，写入 `JRE_HOME` 前还要求实际 `jre` 目录存在。系统 `/usr/bin/java` 占位程序不代表已有可用 JDK 8，也不用于触发系统安装提示。

维护者命令行的 IDEA 项目检查通过 macOS 的 `xmllint` 读取 `.idea/misc.xml`、`.idea/gradle.xml` 和 `${IDEA_CONFIG_DIR}/options/jdk.table.xml`，成员无需 Python。`IDEA_CONFIG_DIR` 默认是 `~/Library/Application Support/JetBrains/IdeaIC2025.3`。扫描保持只读；使用 `--project` 修复已导入项目时会统一 SDK 名称，见 [IDE 指南](ide.md#统一-jdk-8-登记与项目引用)。工具不启动 GUI；设置可解析仍需在 IDEA 中执行 Gradle 同步。

Wrapper 缓存由下载 URL 和项目缓存设置共同决定，仅有 ZIP 或另一个 URL 的同版缓存不算当前项目完整缓存。独立 SDK 安装不依赖该缓存；项目构建则遵循 IDEA 的 Wrapper 或 LOCAL 分发选择。无法可靠解析的配置显示待确认；构建入口无法确定分发时会报错。

## SDK 安装位置与导出变量

| 变量 | 配置后的含义 |
| --- | --- |
| `JAVA_HOME` | 已通过 `java`、`javac` 1.8 验证的实际 JDK Home |
| `JAVA_8_HOME` | 与 `JAVA_HOME` 相同 |
| `JRE_HOME` | 实际存在的 `$JAVA_HOME/jre` |
| `GRADLE_HOME` | 当前终端使用且已登记的独立 Gradle 安装目录 |
| `GRADLE_4_5_1_HOME` | 已配置的 Gradle 4.5.1 安装目录，切换到 6.8 时保留 |
| `GRADLE_6_8_HOME` | 已配置的 Gradle 6.8 安装目录，切换到 4.5.1 时保留 |
| `GRADLE_USER_HOME` | Gradle 用户配置与缓存目录，默认 `~/.gradle` |
| `PATH` | 将 `$JAVA_HOME/bin`、`$GRADLE_HOME/bin` 放在前部并去重 |

默认 JDK 下载目录为 `~/.local/share/java-dev/jdk8`。实际 `JAVA_HOME` 可能位于其内部的 `Contents/Home`；复用已有安装时也可能指向其他用户目录，应以检查输出为准。独立 Gradle 按版本分别安装在 `~/.local/share/java-dev/gradle-4.5.1` 和 `~/.local/share/java-dev/gradle-6.8`。安装登记与默认激活分开。两版可并存，实际当前终端由 gradle_use 选择；普通切换不改新终端默认，--default 同时保存默认并切换。另一版本目录和登记保留。

脚本不设置全局 `CLASSPATH`，也不把项目依赖 JAR 手工加入系统环境。项目依赖由 Gradle 配置管理；用户原有的其他设置会保留。

## 三个受管环境文件

默认配置如下：

```text
~/.config/java-dev/
├── jdk.sh       # JAVA_HOME、JAVA_8_HOME、JRE_HOME
├── gradle.sh    # 版本登记、gradle_use、默认加载、GRADLE_USER_HOME
├── env.sh       # 聚合加载两个模块，并统一维护 PATH
└── gradle-default # 新终端默认的白名单版本字面量，按数据读取
```

`ENV_FILE` 指定聚合文件；`JDK_ENV_FILE`、`GRADLE_ENV_FILE` 默认分别为 `${ENV_FILE%/*}/jdk.sh` 和 `${ENV_FILE%/*}/gradle.sh`。因此自定义聚合文件目录后，两模块默认随之移动，也可分别显式配置。

`GRADLE_DEFAULT_FILE` 默认 `${ENV_FILE%/*}/gradle-default`，只存已登记版本字面量，不 source/eval；新终端只读取配置并选择登记版本，不启动 SDK 探测或联网。生成的 gradle_use 与模块长期保留，不依赖 helper 下载临时目录。

Shell 入口使用 `. '聚合文件绝对路径'` 加载环境，默认写入 Zsh 的 `~/.zshrc` 或 Bash 的 `~/.bash_profile`。脚本仅更新下列标记之间的受管区块，保留其他内容：

```text
# >>> team-java-env managed >>>
…受管配置…
# <<< team-java-env managed <<<
```

旧版单文件 `env.sh` 的内容会保留，新区块负责加载完整模块。首次改写已有文件时保存同路径 `.bak`；已有备份不覆盖。相同配置重复执行不会重复追加加载行或更新时间。Shell 中的工具加载区块会放在文件末尾，避免后续的旧变量再次覆盖 SDK 设置。

写入后会验证完整变量、命令路径和终端配置加载结果。终端配置加载使用限时、无输入的独立非交互子进程；若配置中提前返回、等待输入或仍然覆盖变量，验证失败会写入对应日志或底层修复历史，不能仅以“文件已写入”判成功。此检查不等于启动完整的交互终端；有交互专用配置时，应按失败日志检查守卫条件与加载顺序。

helper/TUI 在子进程内验证配置，无法改变父终端；新开终端或在当前终端执行实际结果中的加载命令。默认路径示例：

```bash
source "$HOME/.config/java-dev/env.sh"
java -version
javac -version
gradle --version
```

修改过 `ENV_FILE` 时使用实际路径。IDEA 的项目 SDK、Gradle JVM 和 Gradle 分发仍需按 [IDE 指南](ide.md#必要设置)配置。

## JDK 8 修复

安装页选择 jdk 会复用已验证的 JDK 8，或从团队内网下载对应 Mac 架构的包；未知或不完整的已有安装目录不会被直接覆盖。下载后验证包与 JDK 内容，再写入完整变量并验证加载结果。

维护者可单独运行：

```bash
bash dev-kit/.support/scripts/runtime/config-jdk.sh --dry-run
bash dev-kit/.support/scripts/runtime/config-jdk.sh
```

`--dry-run` 不安装、不加载已生成的用户环境，也不执行 SDK。JDK 包应包含可运行的 `bin/java`、`bin/javac` 及 `jre`；支持常见的 `Contents/Home` 内层结构。本流程处理 `tar.gz`，不运行 `.pkg` 安装器。

## Gradle 与项目验证

安装页选择 gradle，版本为 4.5.1、6.8 或 all；安装并登记所选版本，确定一次默认值并验证加载，不构建项目。安装完成后，已安装版本按下列命令切换：

```bash
source "$HOME/.config/java-dev/env.sh"
gradle_use --list
gradle_use 4.5.1
gradle_use 6.8
gradle_use 6.8 --default
gradle --version
```

普通 gradle_use 只影响当前终端及其后续子进程；--default 原子保存新终端默认并切换当前终端。目标目录、执行文件或 launcher JAR 无效，或默认保存失败时保留原环境，不报告成功。PATH 清除受管旧 Gradle bin 后插入目标并刷新命令缓存，不累积旧路径，不破坏 Java/nvm/用户 PATH。切换不下载、不删除缓存、不修改业务 Wrapper 或 IDEA 设置。

维护者底层 --project 才按 IDEA 分发选择 Wrapper/LOCAL，执行 `--no-daemon --console=plain build`；没有 IDEA 配置时使用受管 Gradle 并提示待导入，未知配置失败。项目实际分发必须与目标版本相符。

维护者使用 `repair-env.sh --project` 时会增加 IDEA 项目配置预检，并在组件修复及环境验证之后执行终端构建检查。构建非零退出，或退出零但缺少 `BUILD SUCCESSFUL`，均不能报告构建通过。项目配置待设置以阶段退出码 `2` 记录；SDK 与终端构建通过时，总体退出码为 `0`，仍明确要求完成 IDEA 设置。可通过 `--gradle-version 4.5.1|6.8` 指定目标 Gradle，省略时默认 4.5.1；项目实际分发必须与目标版本相符。具体命令和排错见 [Gradle 指南](gradle.md)。

## 修复历史与结果

统一组件安装在 `~/Library/Logs/team-java-env/components/<本次记录>/` 保存 plan.json、steps.tsv、result.tsv 和组件日志；成功/复用后的实际版本、有效默认、加载与切换指引随结果输出和日志记录。失败、依赖跳过及取消按真实状态呈现，预演不写安装记录。

维护者底层 repair-env.sh 的旧修复历史继续保留在 `~/Library/Logs/team-java-env/history/`：report.md、阶段/最终状态、logs、before/after、config-changes.diff、插件逐项结果及 plugin-backups。运行 history.sh 可查看，详见[历史说明](../repair-history.md)。底层指定项目后，SUCCEEDED 和 PROJECT_BUILD_VERIFIED_IDEA_PENDING 仍不代表 IDEA GUI 同步成功；没有项目就不构建。不要把公共组件报告与底层历史的内容承诺混淆。

## 维护者默认配置

高级配置位于 [env.sh](../../dev-kit/.support/config/env.sh)，环境变量可覆盖：

| 变量 | 默认值或用途 |
| --- | --- |
| `SERVER_ADDR` / `SERVER_SCHEME` | 默认 `127.0.0.1:8080` / `http`；正式分发改为真实内网地址 |
| `JDK_PACKAGE_PATH` | 按架构选择 `resources/runtime/jdk/jdk8-macos-arm64.tar.gz` 或 `jdk8-macos-x64.tar.gz` |
| `JDK_SHA256` / `GRADLE_SHA256` | 从成员资源清单取得固定摘要，也可由维护者显式提供 |
| `JDK_AUTO_DETECT` | 默认 `true`；设为 `false` 关闭系统登记和 PATH 的额外探测 |
| `JDK_INSTALL_DIR` | `~/.local/share/java-dev/jdk8` |
| `GRADLE_VERSION` / `GRADLE_INSTALL_DIR` | 默认 `4.5.1`，可选 `6.8`；默认目录为 `~/.local/share/java-dev/gradle-${GRADLE_VERSION}` |
| `GRADLE_PACKAGE_PATH` | 默认随目标版本选择 `resources/runtime/gradle/gradle-${GRADLE_VERSION}-bin.zip` |
| `GRADLE_USER_HOME` / `GRADLE_BUILD_TASK` | `~/.gradle` / `build`；任务覆盖只能是单一合法任务名 |
| `ENV_FILE` / `JDK_ENV_FILE` / `GRADLE_ENV_FILE` | 上述聚合文件与两个模块文件 |
| `GRADLE_DEFAULT_FILE` | `${ENV_FILE%/*}/gradle-default`，持久默认数据 |
| `SHELL_PROFILE` | 默认随 Shell 选择 `.zshrc` / `.bash_profile` |
| `IDEA_APP` / `IDEA_PLUGINS_DIR` | 个人 IDEA 应用目录及 `IdeaIC2025.3/plugins` 目录 |
| `IDEA_CONFIG_DIR` | `~/Library/Application Support/JetBrains/IdeaIC2025.3`；IDEA 配置与 SDK 登记表位置 |
| `IDEA_JDK_NAME` | `azul-1.8`；修复时统一使用的 JDK 8 SDK 名称 |
| `REPAIR_HISTORY_DIR` | `~/Library/Logs/team-java-env/history` |

`REPAIR_RUN_DIR` 由修复入口为当前运行自动设置，成员不必填写。服务器准备见[服务启动指南](../service-startup.md)，固定包来源见[运行环境来源](../resources/runtime-sources.md)。安装包齐全不代表业务依赖已缓存；完全离线构建仍需项目维护者准备依赖并验证。
