# IDEA 与全部插件修复

团队基线为 **IntelliJ IDEA Community 2024.3.7.1**，应用安装在 **`~/Applications/IntelliJ IDEA CE.app`**。这是当前用户的个人应用目录，与系统 `/Applications` 不同；工具使用当前 `HOME`，不要求填写用户名或运行 `sudo`。

菜单 `1` 固定安装配置 JDK 8、Gradle 4.5.1、IDEA 和全部六个推荐插件；菜单 `4` 单独安装 IDEA，菜单 `5` 安装并验证全部六个推荐插件。仅下载功能保留为维护者命令行入口，下载 ZIP 不等于插件已经安装。

## 操作前退出 IDEA

先保存项目和未保存文件，再正常退出 IDEA，确认应用已关闭后运行插件修复或 SDK 名称同步。工具不会自动结束或强制杀掉 IDEA 进程；IDEA 尚在运行时，应按提示退出后重试。

安装结束后工具不自动打开 IDEA。首次启动及插件实际功能仍需在 IDEA 中确认，不能把文件校验通过说成已验证了所有 IDE 功能。

## IDEA 应用安装

菜单 `4` 显示当前用户 `$HOME/Applications` 的实际路径，并按 Mac 架构从内网下载或复用 DMG，校验固定 SHA-256 后只读挂载。安装前检查社区版 bundle ID、短版本、构建号和可执行文件；复制到个人应用目录的临时位置后再次检查，最后保存到目标路径。

已有同版本、同构建号且完整的应用会复用；其他版本、不完整目标或符号链接会保留并报错，不直接覆盖。`~/Applications` 若是指向其他位置的符号链接，安装器也会拒绝，避免意外写入系统目录。

完成后在 Finder 中按 `Command + Shift + G`，输入：

```text
~/Applications
```

然后手动打开 `IntelliJ IDEA CE.app`。若挂载卷未能卸载，工具会保留挂载目录并显示路径；先关闭占用该卷的程序，再正常卸载，不必强制卸载其他卷。

需要手动安装时，也应把 DMG 中的应用复制到这个个人目录。DMG 内的 `Applications` 快捷方式通常指向系统 `/Applications`，不是本工具约定的安装位置。

## 六个插件默认全部安装

| 插件 | 固定版本 | 主要用途 |
| --- | --- | --- |
| Database Navigator | 4.1.0.3 | 在 IDEA 中查看数据库 |
| MyBatisX | 1.7.6 | MyBatis Mapper 接口与 XML 导航 |
| GenerateAllSetter | 2.8.5 | 生成 setter 调用 |
| GsonFormatPlus | 1.6.1 | 根据 JSON 生成 Java 对象代码 |
| Key Promoter X | 2026.1.2 | 提示操作对应的快捷键 |
| Lombok | 243.28141.18 | 让 IDEA 识别 Lombok 生成的构造器、getter 和 setter |

这些版本与团队 IDEA 2024 基线配套。固定来源和兼容范围见[插件来源说明](../resources/plugin-sources.md)，不要直接替换为 Marketplace 最新版。

默认插件目录为：

```text
~/Library/Application Support/JetBrains/IdeaIC2024.3/plugins
```

维护者可通过 `IDEA_PLUGINS_DIR` 指定其他受控目录；应用位置由 `IDEA_APP` 表示。修复流程会对全部目标插件逐项安装和验证，最终报告实际结果。需要替换原插件时，旧目录保存在**本次修复历史**的 `plugin-backups/`；用户其他插件不应当作这六个插件的安装结果。

操作步骤：

1. 保存工作并退出 IDEA。
2. 使用菜单 `1` 一键安装并配置全部环境，或在 IDEA 已就绪时使用菜单 `5`。
3. 检查插件逐项结果和整体结果；失败时打开输出的本次历史目录，查看对应日志和备份。
4. 手动启动 IDEA，在 Plugins 页面确认六个插件显示正常，再在真实项目中使用相关功能。

只想下载或手动安装时，由维护者运行 `bash dev-kit/.support/scripts/download-tools.sh`，选择需要的插件。原始 ZIP 默认保存在 `~/Downloads/team-java-env/plugins/idea/`，可在 IDEA 的 `Settings → Plugins → 齿轮 → Install Plugin from Disk` 中选择 ZIP，按提示重启；手动磁盘安装不需要先解压 ZIP。自动安装与手动安装应使用同一组固定版本。下载命令需要已打包工具中的资源清单；在完整工具目录运行时，将脚本路径改为 `.support/scripts/download-tools.sh`。

## Lombok 安装与启用步骤

菜单 `1` 和 `5` 已包含 Lombok；自动安装完成后，从第 4 步开始检查。需要单独手动安装时，按以下步骤操作：

1. 由维护者运行 `bash dev-kit/.support/scripts/download-tools.sh --id lombok`，得到 `~/Downloads/team-java-env/plugins/idea/lombok-243.28141.18.zip`。
2. 打开 IDEA，在 macOS 顶部菜单选择 `IntelliJ IDEA → Settings… → Plugins`（旧版本设置菜单可能叫 `Preferences…`）。
3. 点击 Plugins 页的齿轮，选择 `Install Plugin from Disk…`，选中上述原始 ZIP，点击 `OK`，按提示重启 IDEA。无需先解压 ZIP。[IDEA 官方安装说明](https://www.jetbrains.com/help/idea/managing-plugins.html)
4. 进入 `Settings → Plugins → Installed`，搜索 `Lombok`，确认已启用；若显示 `Enable`，点击启用并按提示重启。
5. 进入 `Settings → Build, Execution, Deployment → Compiler → Annotation Processors`，勾选 `Enable annotation processing` 和 `Obtain processors from project classpath`，点击 `Apply → OK`。[IDEA 官方注解处理说明](https://www.jetbrains.com/help/idea/annotation-processors-support.html)
6. 重新加载 Gradle 项目，检查使用 `@RequiredArgsConstructor` 的类是否仍提示 `final` 字段未初始化，并完成真实项目构建验证。

IDEA Lombok 插件用于编辑器识别，业务项目仍需在 `build.gradle` 中声明 Lombok 依赖。IDE 插件版本 `243.28141.18` 与项目使用的 Lombok 库版本分别管理；团队 Gradle 4.5.1 的依赖处理见[项目依赖说明](dependencies.md#gradle-451-与-lombok)。

## 必要设置

SDK 配置完成后，在 IDEA 中检查：

1. **项目 JDK**：确认 Project Structure 的 SDK 为 `IDEA_JDK_NAME`，默认 `azul-1.8`，并指向实际 `JAVA_HOME` 对应的 JDK 8。尚未导入的项目先完成导入，再运行名称同步。默认下载外层目录是 `~/.local/share/java-dev/jdk8`，真实 JDK Home 可能位于其内部 `Contents/Home`；复用已有 JDK 时路径也可能不同。
2. **Gradle 分发**：在 `Settings → Build Tools → Gradle` 中确认项目使用 Wrapper 还是本地安装。选本地安装时，目录填实际 `GRADLE_HOME`，按所选版本为 `~/.local/share/java-dev/gradle-4.5.1` 或 `~/.local/share/java-dev/gradle-6.8`；选 Wrapper 时，项目需有完整可执行的 Wrapper，并使用团队要求的 Gradle 版本。
3. **Gradle JVM**：确认使用同一个 `IDEA_JDK_NAME`。IDEA 自带运行时用于 IDE 本身，不等于项目或 Gradle 的 JDK。`Project SDK`、`JAVA_HOME` 是引用入口，仍可能显示在下拉列表中。
4. **注解处理**：项目使用 Lombok 时，按上面的安装与启用步骤检查 annotation processing；Gradle 构建中的处理器依赖仍由业务项目维护。
5. **项目导入与功能**：导入真实业务项目，执行 `Reload All Gradle Projects`，再核对依赖仓库、运行配置、数据库连接及插件实际功能。

终端构建验证遵循 IDEA 中关联项目的分发选择：Wrapper 使用 `./gradlew`，LOCAL 使用配置中的实际 `gradleHome/bin/gradle`；未知配置会报错。尚无 IDEA 项目配置时，使用受管独立 `GRADLE_HOME` 并提示待导入。Wrapper 缓存不应当作受管独立安装的 `GRADLE_HOME`。

## 只读项目预检

维护者通过 `check-env.sh --project` 或 `repair-env.sh --project` 指定项目后，会使用 macOS 的 `xmllint` 读取项目的 `.idea/misc.xml`、`.idea/gradle.xml`，以及 `${IDEA_CONFIG_DIR}/options/jdk.table.xml`。`IDEA_CONFIG_DIR` 默认是 `~/Library/Application Support/JetBrains/IdeaIC2024.3`。成员无需安装 Python；菜单不选择或检查业务项目。

预检检查 Project SDK、Gradle JVM 是否已登记且指向有效 JDK 8，以及 LOCAL 的 Gradle 目录等信息；待配置时打印实际 JDK/Gradle 路径和 IDEA 设置入口。它不会自动写入用户 IDEA 配置，也不会启动 GUI。自定义配置目录时，可由维护者设置 `IDEA_CONFIG_DIR` 后运行：

```bash
bash dev-kit/.support/scripts/check-idea-project.sh --project "/absolute/path/to/java-project"
bash dev-kit/.support/scripts/check-idea-project.sh --project "/absolute/path/to/java-project" --dry-run
```

已选项目待配置时，`check-env.sh` 返回 `1`；修复中的项目预检以待配置状态、阶段退出码 `2` 记录，不替代后续 SDK 和终端构建验证。二者通过时总体退出 `0`，结果为 `PROJECT_BUILD_VERIFIED_IDEA_PENDING`，仍需手动设置 IDEA。静态设置可解析时，`SUCCEEDED` 也只表示修复及终端构建通过，不能确认 IDEA 已同步成功。

终端环境和 IDEA 设置需要分别确认。查看已生成变量可在新终端运行：

```bash
source "$HOME/.config/java-dev/env.sh"
printf '%s\n' "$JAVA_HOME" "$JAVA_8_HOME" "$JRE_HOME" "$GRADLE_HOME" "$GRADLE_4_5_1_HOME"
```

自定义过 `ENV_FILE` 时使用实际文件。IDEA 安装成功、插件安装验证通过和 SDK 版本通过，都不能替代项目构建；由维护者使用 `repair-env.sh --project` 完成带项目的修复和构建，或使用[独立构建验证入口](gradle.md#维护者命令行)。

## 统一 JDK 8 登记与项目引用

维护者通过 `repair-env.sh --project` 指定已导入 IDEA 的项目，并选择全部或 JDK、Gradle、IDEA 修复范围时，使用 `IDEA_JDK_NAME`（默认 `azul-1.8`）统一名称：

- 在 `${IDEA_CONFIG_DIR}/options/jdk.table.xml` 中登记实际 JDK 8 Home，并将指向同一物理目录的其他名称合并。
- 更新所选项目 `.idea/misc.xml` 的 Project SDK、`.idea/gradle.xml` 当前关联项目的 Gradle JVM，以及现有模块中引用被合并名称的显式 SDK 设置。
- 保留其他 JDK、其他 Gradle 项目关联及 Wrapper / LOCAL 分发设置；首次改写已有文件保存 `.bak`，重复运行相同配置不再改写。

执行前须完全退出 IDEA，避免 IDE 保存内存中的旧配置覆盖修复结果。同名 SDK 指向另一目录、XML 无法安全解析、配置或模块路径不在允许范围时，在改写前报错。尚未导入的项目返回待配置状态，不生成新的分发设置。

单独运行时，不安装其他组件或执行项目构建：

```bash
bash dev-kit/.support/scripts/runtime/config-idea-sdk.sh --project "/absolute/path/to/java-project" --dry-run
bash dev-kit/.support/scripts/runtime/config-idea-sdk.sh --project "/absolute/path/to/java-project"
```

维护者可通过 `IDEA_JDK_NAME` 指定另一固定名称，并让团队所有项目使用同一配置。名称同步仅迁移所选项目；其他项目若仍引用被合并的旧名称，也应逐一运行该入口，否则 IDEA 可能为满足旧引用再次登记。删除 SDK 名称不会删除 JDK 安装目录。

同步完成后启动 IDEA，执行 `Reload All Gradle Projects`。`Project SDK` 和 `JAVA_HOME` 两个引用入口仍会显示，这与同目录的重复 SDK 登记不同。

## 历史与其他资源

每次修复开始后，成功或失败均记录到 `~/Library/Logs/team-java-env/history/<本次记录>/`。`report.md` 汇总步骤，`steps.tsv` / `result.tsv` 记录状态，`config-changes.diff` 展示配置差异；插件阶段有逐项结果与必要的 `plugin-backups/`。可直接打开历史目录，或运行 `bash dev-kit/.support/scripts/history.sh` 查看记录；`--dry-run` 不创建历史。

DBeaver 由维护者通过 `download-tools.sh` 选择并下载 DMG 后手动安装。Database Navigator 或 DBeaver 首次连接数据库可能需要额外 JDBC 驱动；业务依赖、驱动、数据库连接和 MySQL 镜像不因 IDEA 安装完成而自动准备好。
