# 独立安装 Gradle 4.5.1 / 6.8 与验证项目构建

工具在用户目录按版本安装独立 Gradle 4.5.1 或 6.8，并配置完整环境变量，两者均使用 JDK 8。维护者通过命令行验证项目构建时，按 IDEA 关联项目的分发设置选择 Wrapper 或 LOCAL 实际目录；尚无 IDEA 配置时使用受管独立 Gradle，并提示待导入。**Wrapper 缓存不是独立安装，`--version` 成功也不能代替构建成功。**

成员运行 `bash devtool-helper.sh install`，勾选 gradle，左右键选择 4.5.1、6.8 或 all，Enter 直接预检并安装。JDK 8 依赖会补入并只计一次；空选择或预检失败不执行。全量默认 4.5.1。成员不选择项目或构建，维护者底层 --project 才执行业务验证。

## 安装位置与环境变量

| 项目 | 默认值 |
| --- | --- |
| `GRADLE_INSTALL_DIR` | 按版本为 `~/.local/share/java-dev/gradle-4.5.1` 或 `~/.local/share/java-dev/gradle-6.8` |
| `GRADLE_HOME` | 当前终端使用且已登记的独立安装目录 |
| `GRADLE_4_5_1_HOME` | 已配置的 4.5.1 安装目录，切换版本时保留 |
| `GRADLE_6_8_HOME` | 已配置的 6.8 安装目录，切换版本时保留 |
| `GRADLE_USER_HOME` | `~/.gradle`，用于 Gradle 用户配置、依赖等缓存 |
| `PATH` | 优先使用 `$JAVA_HOME/bin` 和 `$GRADLE_HOME/bin`，重复项去重 |

两个版本目录独立保存，切换当前版本不会删除另一版本目录或已配置的版本别名。安装目录和缓存目录用途不同：受管独立 Gradle 程序放在 `GRADLE_HOME`，Wrapper 分发缓存通常位于 `~/.gradle/wrapper/dists`。IDEA 选择 Wrapper 时，项目构建通过 `./gradlew` 使用其分发，不把该缓存当作受管独立安装目录。

变量写入 `${ENV_FILE%/*}/gradle.sh`，默认由 `~/.config/java-dev/env.sh` 聚合加载；完整 JDK 变量也一并检查和配置。环境文件、Shell 入口、首次备份和幂等规则见[运行环境指南](runtime.md#三个受管环境文件)。

## 安装前准备

- 已有完整 **JDK 8**，包括可运行的 `java`、`javac` 与实际 `jre` 目录。可勾选 jdk 单独配置；gradle 会自动补入 JDK 8 依赖并显示在当前选择页。
- 团队内网服务可以提供 Gradle ZIP，成员清单中具有对应固定 SHA-256。新的独立安装不接受没有固定摘要的下载。
- 要验证构建时，准备真实业务项目，其根目录包含 `build.gradle` 或 `build.gradle.kts`。本地分发不要求 Wrapper；IDEA 选择 Wrapper 时，必须有 `gradlew`、Wrapper JAR 和 properties，且 `gradlew` 可执行。

Gradle 安装包不包含项目的 Maven 依赖、Gradle 插件和企业仓库凭据。项目构建可能仍需访问团队依赖仓库；文件已经下载到电脑，不代表所有业务依赖已满足。

## 修复过程与成功标准

1. 检查已有 JDK 8、目标目录及配置路径。未知或不完整的已有 Gradle 安装目录会保留并报错，不直接覆盖。
2. 已有完整同版分发时，实际运行其 `bin/gradle --version` 核对版本后复用。缺少时从内网下载固定 ZIP，校验 SHA-256、归档路径和分发结构，验证版本后保存到用户目录。
3. 写入完整 JDK/Gradle 环境模块，加载验证变量和 Java/Gradle 命令路径；只显示“复制完成”不算这一步成功。
4. 公共组件入口或底层命令未指定项目时，报告 SDK 安装及环境验证结果，并明确未构建。维护者通过 `--project` 指定项目时，读取 IDEA 分发设置：Wrapper 调用 `./gradlew`，LOCAL 调用实际 `gradleHome/bin/gradle`；未知或不可解析的配置报错。无 IDEA 项目配置时，调用受管 `$GRADLE_HOME/bin/gradle` 并提示待导入。先验证实际命令的版本，再进入项目，附加以下参数执行构建：

   ```text
   --no-daemon --console=plain build
   ```

5. 构建同时满足**退出码为零**、输出含 **`BUILD SUCCESSFUL`**，才报告项目构建验证通过。非零退出码按原值返回；即使退出零，没有成功标记也算失败。

维护者使用 `repair-env.sh --project` 时，IDEA 项目配置另做只读预检。SDK 与终端构建通过、IDEA 仍待配置时，修复结果为 `PROJECT_BUILD_VERIFIED_IDEA_PENDING`，总体退出 `0`，但仍需手动设置 IDEA。`SUCCEEDED` 也不能证明 GUI 已同步成功；需启动 IDEA 并执行 `Reload All Gradle Projects`，见[IDE 预检说明](ide.md#只读项目预检)。

默认 `build` 不添加跳过测试的参数。它会执行项目定义的编译、测试及相关任务，可能更新项目的 `build/` 和 Gradle 缓存。维护者确有需要时，可通过 `GRADLE_BUILD_TASK` 指定一个任务，如 `:service:build`；不能传入多个任务、命令行选项、空白或 Shell 命令。改变任务后，以报告记录的实际任务为准，不能把局部任务通过说成完整默认构建通过。

## 多版本安装与切换

4.5.1/6.8 分别验证并登记后，按计划一次确定默认：单版设为默认；all 保留已有有效默认，无有效默认用 4.5.1，不由最后安装者决定。部分失败不把失败版本设为默认，保留有效旧默认。生成模块随聚合 env.sh 长期加载，安装结果按实际成功版本给出指引：

```bash
# 原终端立即使用；也可新开终端。ENV_FILE 自定义时改实际路径
source "$HOME/.config/java-dev/env.sh"
gradle_use --list
gradle_use 4.5.1          # 当前终端及其后续子进程
gradle_use 6.8           # 前提是该版已安装登记
gradle_use 6.8 --default # 保存新终端默认，并切换当前终端
gradle --version
```

`GRADLE_DEFAULT_FILE` 默认 `${ENV_FILE%/*}/gradle-default`，按数据读取白名单字面量，原子保存，不 source/eval。新终端加载只选择已登记版本，不启动 SDK 探测或下载；目标无效/默认保存失败保持原环境。切换清理确切受管 Gradle bin 项、刷新 Bash/Zsh 命令缓存，不累积旧 PATH，也不影响 Java/nvm。

helper/TUI 无法修改父终端，结果中的安装验证不表示当前终端已切换。切换无需 helper、网络或保留临时目录，不修改项目 Wrapper、IDEA 已设 GradleHome 和用户缓存。IDEA 使用 LOCAL 时自行确认实际目录；项目选择 Wrapper 时仍按 Wrapper 执行。

统一安装记录位于 `~/Library/Logs/team-java-env/components/`，底层 repair-env.sh 的完整修复历史仍在 history/。卸载可选择某一受管版本，只清理该登记及默认引用，保留其他版本和 JDK；默认引用失效时不自动选另一版，重新加载后核对列表并显式设置，见[卸载指南](cleanup.md)。

## 维护者命令行

以下命令在本工具仓库根目录执行。正式下载应使用已配置团队地址、固定摘要清单的工具包；直接调试源码时，维护者也可显式提供 `GRADLE_SHA256`。

```bash
# 只预览：不加载生成的环境、不执行 SDK、不下载或构建
bash dev-kit/.support/scripts/runtime/install-gradle.sh --project "/absolute/path/to/java-project" --dry-run

# 没有项目：安装/复用独立 Gradle，补齐环境并验证版本
bash dev-kit/.support/scripts/runtime/install-gradle.sh

# 有项目：安装/复用后按 IDEA 分发选择执行终端构建验证
bash dev-kit/.support/scripts/runtime/install-gradle.sh --project "/absolute/path/to/java-project"

# SDK 已就绪时，单独验证业务项目
bash dev-kit/.support/scripts/runtime/verify-gradle.sh --project "/absolute/path/to/java-project"

# 需要完整修复历史时使用底层 Java 修复入口；默认版本为 4.5.1
bash dev-kit/.support/scripts/repair-env.sh --scope gradle --project "/absolute/path/to/java-project"

# 安装 Gradle 6.8；省略项目时不执行构建
bash dev-kit/.support/scripts/repair-env.sh --scope gradle --gradle-version 6.8

# 验证使用 Gradle 6.8 的业务项目
bash dev-kit/.support/scripts/repair-env.sh --scope gradle --gradle-version 6.8 --project "/absolute/path/to/java-project"
```

`repair-env.sh` 支持 `--gradle-version 4.5.1|6.8`，JDK 固定使用 8；这是维护者底层单版安装参数，公共 --gradle-version 另支持 all；已经安装后使用 gradle_use 切换。切换 SDK 不会自动升级业务项目的 Wrapper、依赖或 IDEA 分发配置。

加载已生成环境后，可手工查看程序路径与版本：

```bash
source "$HOME/.config/java-dev/env.sh"
printf '%s\n' "$JAVA_HOME" "$GRADLE_HOME" "$GRADLE_USER_HOME"
java -version
javac -version
"$GRADLE_HOME/bin/gradle" --version
```

这些版本命令仅证明 SDK 可以运行。实际构建结果仍以 `verify-gradle.sh` 或统一修复入口的构建阶段为准。本仓库不是业务项目，不要把它当作 `--project` 的目标。

## 兼容已有 Wrapper

独立 SDK 安装与 Wrapper 配置分别管理。IDEA 选择 Wrapper 时，构建验证会实际运行 `./gradlew`。团队需要维护其下载地址时，可运行：

```bash
bash dev-kit/.support/scripts/runtime/config-gradle.sh --project "/absolute/path/to/java-project" --dry-run
bash dev-kit/.support/scripts/runtime/config-gradle.sh --project "/absolute/path/to/java-project"
```

这个配置脚本要求项目已有 `gradlew`、`gradle/wrapper/gradle-wrapper.jar` 和 `gradle-wrapper.properties`。修改前先确认目标下载 URL 对应的完整解压缓存，或通过 HTTP HEAD 确认目标 URL 可达；不可达时不修改配置、备份或权限。它不会强制换成官方源，`--dry-run` 不访问网络。

检查通过后，只更新分发地址、可取得的 SHA-256 和执行权限，首次修改保留 `gradle-wrapper.properties.bak`。配置完成不等于 Wrapper 已实际运行，仍需执行版本及构建验证。

Wrapper 缓存与 URL、`distributionBase`、`distributionPath`、`zipStoreBase`、`zipStorePath` 有关。静态扫描发现 ZIP 不代表解压安装已完成；发现其他 URL 的同版本缓存也不等于目标 URL 的缓存完整。无法可靠解析时标为待确认，实际使用哪种分发仍以 IDEA 项目配置为准。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 缺少 JDK 8 或 `jre` | 在安装页选 jdk 修复完整 JDK，再检查 `JAVA_HOME`、`JAVA_8_HOME`、`JRE_HOME` |
| 提示安装目录未知、不完整或版本不符 | 保留原目录，确认它的用途；另设用户安装目录或由维护者处理，不直接覆盖 |
| 提示缺少 SHA-256 | 使用维护者打包的最新成员清单，或由维护者提供已核验的固定摘要 |
| 下载出现 403/404 或连接失败 | 维护者检查服务和资源路径，见[服务启动指南](../service-startup.md) |
| SHA-256 不匹配或归档异常 | 停止安装，核对源包、清单与发布文件；不要关闭校验或只修改摘要 |
| 新终端仍使用旧版本 | 检查 Shell 加载入口、三个受管文件及 `PATH`；在修复历史中查看配置差异 |
| 版本验证通过，但项目构建失败 | 查看构建日志；检查业务代码、测试、依赖仓库、权限和项目版本要求，不能算作整体成功 |
| 提示 IDEA 分发未知或 LOCAL 目录无效 | 在 `Settings → Build Tools → Gradle` 确认分发方式及实际目录后重新验证 |
| 终端构建通过，但 IDEA 项目待配置 | 按输出的 JDK/Gradle 路径设置 Project SDK 与 Gradle JVM，再手动导入并同步 |
| 退出零却提示缺少成功标记 | 输出未提供可确认的 Gradle 构建成功结果，按失败处理并交由维护者检查 |

维护者底层修复历史默认在 `~/Library/Logs/team-java-env/history/<本次记录>/`，失败也保存。固定资源来源见[运行环境来源](../resources/runtime-sources.md)；本工具的隔离测试不等于已在真实业务项目完成构建，实际平台和项目组合仍应以本次验证结果为准。
