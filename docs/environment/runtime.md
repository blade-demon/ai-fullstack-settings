# JDK、Gradle 与完整环境配置

本工具面向 macOS，团队目标为 **JDK 8、独立安装的 Gradle 4.5.1、IDEA 2024.3.7.1 社区版及配套插件**。SDK 安装在用户目录，不使用 `sudo`。本仓库是环境工具，不是 Java 业务项目。

## 成员修复流程

启动「开始配置.command」后先看扫描结果。有业务项目时，先用菜单 `3` 选择包含 `build.gradle` 或 `build.gradle.kts` 的根目录，然后保存工作、退出 IDEA，再用菜单 `1` 一键修复。未选项目也可修复全部环境，但最终只报告环境验证通过，并明确未执行项目构建。

| 菜单 | 用途 |
| --- | --- |
| `1` | 修复 JDK、独立 Gradle、IDEA 和全部六个插件，完成最终验证 |
| `2` | 修复 JDK 8 及完整 JDK 环境变量 |
| `3` | 选择项目后重新扫描，不开始安装或构建 |
| `7` | 修复独立 Gradle；有选定项目时必须实际构建 |
| `8` / `9` | 修复 IDEA / 安装验证全部插件；插件安装前须退出 IDEA |
| `10` | 查看各次修复结果、日志和配置差异 |

其他菜单保留：`4` / `5` 启停 MySQL，`6` 仅下载软件或插件，`0` 退出。项目构建、IDE 设置与插件操作分别见 [Gradle 指南](gradle.md)和 [IDE 指南](ide.md)。

## 环境预检

扫描同时关注安装状态和持久化配置：JDK 是否为完整 1.8、独立 Gradle 是否为目标 4.5.1、IDEA 是否为团队版本，以及受管环境和 Shell 入口是否完整。已选项目时，还会只读检查 IDEA 的 Project SDK、Gradle JVM 和分发设置；待配置时 `check-env.sh` 返回 `1` 并打印实际路径及设置入口。扫描不会开始安装或业务构建；静态检查不能替代实际版本验证、终端构建或 IDEA 同步。

JDK 探测依次考虑已生成环境文件中的 `JAVA_HOME`、当前环境的 `JAVA_HOME`、`JDK_INSTALL_DIR`；`JDK_AUTO_DETECT=true` 时还检查系统登记与可识别的 PATH JDK。只有 `java`、`javac` 都符合 1.8 才采用，写入 `JRE_HOME` 前还要求实际 `jre` 目录存在。系统 `/usr/bin/java` 占位程序不代表已有可用 JDK 8，也不用于触发系统安装提示。

IDEA 项目检查通过 macOS 的 `xmllint` 读取 `.idea/misc.xml`、`.idea/gradle.xml` 和 `${IDEA_CONFIG_DIR}/options/jdk.table.xml`，成员无需 Python。`IDEA_CONFIG_DIR` 默认是 `~/Library/Application Support/JetBrains/IdeaIC2024.3`。扫描保持只读；修复所选的已导入项目时会统一 SDK 名称，见 [IDE 指南](ide.md#统一-jdk-8-登记与项目引用)。工具不启动 GUI；设置可解析仍需在 IDEA 中执行 Gradle 同步。

Wrapper 缓存由下载 URL 和项目缓存设置共同决定，仅有 ZIP 或另一个 URL 的同版缓存不算当前项目完整缓存。独立 SDK 安装不依赖该缓存；项目构建则遵循 IDEA 的 Wrapper 或 LOCAL 分发选择。无法可靠解析的配置显示待确认；构建入口无法确定分发时会报错。

## SDK 安装位置与导出变量

| 变量 | 配置后的含义 |
| --- | --- |
| `JAVA_HOME` | 已通过 `java`、`javac` 1.8 验证的实际 JDK Home |
| `JAVA_8_HOME` | 与 `JAVA_HOME` 相同 |
| `JRE_HOME` | 实际存在的 `$JAVA_HOME/jre` |
| `GRADLE_HOME` | 已通过版本验证的独立 Gradle 安装目录 |
| `GRADLE_4_5_1_HOME` | 团队 4.5.1 基线下与 `GRADLE_HOME` 相同 |
| `GRADLE_USER_HOME` | Gradle 用户配置与缓存目录，默认 `~/.gradle` |
| `PATH` | 将 `$JAVA_HOME/bin`、`$GRADLE_HOME/bin` 放在前部并去重 |

默认 JDK 下载目录为 `~/.local/share/java-dev/jdk8`。实际 `JAVA_HOME` 可能位于其内部的 `Contents/Home`；复用已有安装时也可能指向其他用户目录，应以检查输出为准。独立 Gradle 默认安装在 `~/.local/share/java-dev/gradle-4.5.1`。

脚本不设置全局 `CLASSPATH`，也不把项目依赖 JAR 手工加入系统环境。项目依赖由 Gradle 配置管理；用户原有的其他设置会保留。

## 三个受管环境文件

默认配置如下：

```text
~/.config/java-dev/
├── jdk.sh       # JAVA_HOME、JAVA_8_HOME、JRE_HOME
├── gradle.sh    # GRADLE_HOME、GRADLE_4_5_1_HOME、GRADLE_USER_HOME
└── env.sh       # 聚合加载两个模块，并统一维护 PATH
```

`ENV_FILE` 指定聚合文件；`JDK_ENV_FILE`、`GRADLE_ENV_FILE` 默认分别为 `${ENV_FILE%/*}/jdk.sh` 和 `${ENV_FILE%/*}/gradle.sh`。因此自定义聚合文件目录后，两模块默认随之移动，也可分别显式配置。

Shell 入口使用 `. '聚合文件绝对路径'` 加载环境，默认写入 Zsh 的 `~/.zshrc` 或 Bash 的 `~/.bash_profile`。脚本仅更新下列标记之间的受管区块，保留其他内容：

```text
# >>> team-java-env managed >>>
…受管配置…
# <<< team-java-env managed <<<
```

旧版单文件 `env.sh` 的内容会保留，新区块负责加载完整模块。首次改写已有文件时保存同路径 `.bak`；已有备份不覆盖。相同配置重复执行不会重复追加加载行或更新时间。Shell 中的工具加载区块会放在文件末尾，避免后续的旧变量再次覆盖 SDK 设置。

写入后会验证完整变量、命令路径和终端配置加载结果。终端配置加载使用限时、无输入的独立非交互子进程；若配置中提前返回、等待输入或仍然覆盖变量，验证失败会写入修复历史，不能仅以“文件已写入”判成功。此检查不等于启动完整的交互终端；有交互专用配置时，应按失败日志检查守卫条件与加载顺序。

新开终端即可加载配置；当前终端执行：

```bash
source "$HOME/.config/java-dev/env.sh"
java -version
javac -version
gradle --version
```

修改过 `ENV_FILE` 时使用实际路径。IDEA 的项目 SDK、Gradle JVM 和 Gradle 分发仍需按 [IDE 指南](ide.md#必要设置)配置。

## JDK 8 修复

菜单 `2` 会复用已验证的 JDK 8，或从团队内网下载对应 Mac 架构的包；未知或不完整的已有安装目录不会被直接覆盖。下载后验证包与 JDK 内容，再写入完整变量并验证加载结果。

维护者可单独运行：

```bash
bash dev-kit/.support/scripts/runtime/config-jdk.sh --dry-run
bash dev-kit/.support/scripts/runtime/config-jdk.sh
```

`--dry-run` 不安装、不加载已生成的用户环境，也不执行 SDK。JDK 包应包含可运行的 `bin/java`、`bin/javac` 及 `jre`；支持常见的 `Contents/Home` 内层结构。本流程处理 `tar.gz`，不运行 `.pkg` 安装器。

## Gradle 与项目验证

菜单 `7` 安装或复用独立 Gradle，修复完整 SDK 环境。未选择项目时验证 SDK 版本和环境，不运行构建；已选择项目时，按 IDEA 分发选择 Wrapper 或 LOCAL 实际 `gradleHome`，执行 `--no-daemon --console=plain build`，默认包含测试。没有 IDEA 项目配置时使用受管 `GRADLE_HOME` 并提示待导入，未知分发配置会失败。

菜单 `1` 会增加 IDEA 项目配置预检，并在组件修复及环境验证之后执行同样的终端构建检查。构建非零退出，或退出零但缺少 `BUILD SUCCESSFUL`，均不能报告构建通过。项目配置待设置以阶段退出码 `2` 记录；SDK 与终端构建通过时，总体退出码为 `0`，仍明确要求完成 IDEA 设置。具体命令和排错见 [Gradle 指南](gradle.md)。

## 修复历史与结果

菜单修复和 `repair-env.sh` 在开始后为每次运行建立独立历史，默认 `~/Library/Logs/team-java-env/history/<本次记录>/`。失败也保存记录：

- `report.md`：结果、步骤摘要、配置变化和日志入口。
- `steps.tsv`、`result.tsv`：阶段及最终状态、退出码、范围和项目。
- `logs/`：SDK、IDEA、插件和项目构建的实际输出。
- `before/`、`after/`、`config-changes.diff`：配置前后快照及差异；同时保留文件摘要和扫描结果。
- `plugin-backups/`：执行插件替换时保留的旧目录；插件阶段还有逐项结果。

最终结果区分 `SUCCEEDED`（所选修复、SDK 和终端构建通过，IDEA 静态配置可解析）、`PROJECT_BUILD_VERIFIED_IDEA_PENDING`（SDK 和终端构建通过，IDEA 待配置）、未选项目的环境或组件验证通过，以及失败。前两者均需手动启动 IDEA 并同步，不代表 GUI 已可用。菜单 `10` 可查看历史；需要完整汇总记录时使用菜单或 `repair-env.sh`，底层 SDK 脚本仅用于单项调试。预演不创建历史。

## 维护者默认配置

高级配置位于 [env.sh](../../dev-kit/.support/config/env.sh)，环境变量可覆盖：

| 变量 | 默认值或用途 |
| --- | --- |
| `SERVER_ADDR` / `SERVER_SCHEME` | 默认 `127.0.0.1:8080` / `http`；正式分发改为真实内网地址 |
| `JDK_PACKAGE_PATH` | 按架构选择 `resources/runtime/jdk/jdk8-macos-arm64.tar.gz` 或 `jdk8-macos-x64.tar.gz` |
| `JDK_SHA256` / `GRADLE_SHA256` | 从成员资源清单取得固定摘要，也可由维护者显式提供 |
| `JDK_AUTO_DETECT` | 默认 `true`；设为 `false` 关闭系统登记和 PATH 的额外探测 |
| `JDK_INSTALL_DIR` | `~/.local/share/java-dev/jdk8` |
| `GRADLE_VERSION` / `GRADLE_INSTALL_DIR` | `4.5.1` / `~/.local/share/java-dev/gradle-4.5.1` |
| `GRADLE_PACKAGE_PATH` | `resources/runtime/gradle/gradle-4.5.1-bin.zip` |
| `GRADLE_USER_HOME` / `GRADLE_BUILD_TASK` | `~/.gradle` / `build`；任务覆盖只能是单一合法任务名 |
| `ENV_FILE` / `JDK_ENV_FILE` / `GRADLE_ENV_FILE` | 上述聚合文件与两个模块文件 |
| `SHELL_PROFILE` | 默认随 Shell 选择 `.zshrc` / `.bash_profile` |
| `IDEA_APP` / `IDEA_PLUGINS_DIR` | 个人 IDEA 应用目录及 `IdeaIC2024.3/plugins` 目录 |
| `IDEA_CONFIG_DIR` | `~/Library/Application Support/JetBrains/IdeaIC2024.3`；IDEA 配置与 SDK 登记表位置 |
| `IDEA_JDK_NAME` | `azul-1.8`；修复时统一使用的 JDK 8 SDK 名称 |
| `REPAIR_HISTORY_DIR` | `~/Library/Logs/team-java-env/history` |

`REPAIR_RUN_DIR` 由修复入口为当前运行自动设置，成员不必填写。服务器准备见[服务启动指南](../service-startup.md)，固定包来源见[运行环境来源](../resources/runtime-sources.md)。安装包齐全不代表业务依赖已缓存；完全离线构建仍需项目维护者准备依赖并验证。
