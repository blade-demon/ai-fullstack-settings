# IDEA 与全部插件修复

团队基线为 **IntelliJ IDEA Community 2024.3.7.1**，应用安装在 **`~/Applications/IntelliJ IDEA CE.app`**。这是当前用户的个人应用目录，与系统 `/Applications` 不同；工具使用当前 `HOME`，不要求填写用户名或运行 `sudo`。

菜单 `1` 一键修复默认包含 IDEA 和全部五个插件；菜单 `8` 单独修复 IDEA，菜单 `9` 安装并验证全部插件。菜单 `6` 保留仅下载功能，下载 ZIP 不等于插件已经安装。

## 操作前退出 IDEA

先保存项目和未保存文件，再正常退出 IDEA，确认应用已关闭后运行插件修复。工具不会自动结束或强制杀掉 IDEA 进程；IDEA 尚在运行时，应按提示退出后重试。

安装结束后工具不自动打开 IDEA。首次启动及插件实际功能仍需在 IDEA 中确认，不能把文件校验通过说成已验证了所有 IDE 功能。

## IDEA 应用安装

菜单 `8` 按 Mac 架构从内网下载或复用 DMG，校验固定 SHA-256 后只读挂载。安装前检查社区版 bundle ID、短版本、构建号和可执行文件；复制到个人应用目录的临时位置后再次检查，最后保存到目标路径。

已有同版本、同构建号且完整的应用会复用；其他版本、不完整目标或符号链接会保留并报错，不直接覆盖。`~/Applications` 若是指向其他位置的符号链接，安装器也会拒绝，避免意外写入系统目录。

完成后在 Finder 中按 `Command + Shift + G`，输入：

```text
~/Applications
```

然后手动打开 `IntelliJ IDEA CE.app`。若挂载卷未能卸载，工具会保留挂载目录并显示路径；先关闭占用该卷的程序，再正常卸载，不必强制卸载其他卷。

需要手动安装时，也应把 DMG 中的应用复制到这个个人目录。DMG 内的 `Applications` 快捷方式通常指向系统 `/Applications`，不是本工具约定的安装位置。

## 五个插件默认全部安装

| 插件 | 固定版本 | 主要用途 |
| --- | --- | --- |
| Database Navigator | 4.1.0.3 | 在 IDEA 中查看数据库 |
| MyBatisX | 1.7.6 | MyBatis Mapper 接口与 XML 导航 |
| GenerateAllSetter | 2.8.5 | 生成 setter 调用 |
| GsonFormatPlus | 1.6.1 | 根据 JSON 生成 Java 对象代码 |
| Key Promoter X | 2026.1.2 | 提示操作对应的快捷键 |

这些版本与团队 IDEA 2024 基线配套。固定来源和兼容范围见[插件来源说明](../resources/plugin-sources.md)，不要直接替换为 Marketplace 最新版。

默认插件目录为：

```text
~/Library/Application Support/JetBrains/IdeaIC2024.3/plugins
```

维护者可通过 `IDEA_PLUGINS_DIR` 指定其他受控目录；应用位置由 `IDEA_APP` 表示。修复流程会对全部目标插件逐项安装和验证，最终报告实际结果。需要替换原插件时，旧目录保存在**本次修复历史**的 `plugin-backups/`；用户其他插件不应当作这五个插件的安装结果。

操作步骤：

1. 保存工作并退出 IDEA。
2. 使用菜单 `1` 一键修复，或在 IDEA 已就绪时使用菜单 `9`。
3. 检查插件逐项结果和整体结果；失败时从菜单 `10` 打开本次历史，查看对应日志和备份。
4. 手动启动 IDEA，在 Plugins 页面确认五个插件显示正常，再在真实项目中使用相关功能。

只想下载或手动安装时，使用菜单 `6`。原始 ZIP 默认保存在 `~/Downloads/team-java-env/plugins/idea/`，可在 IDEA 的 `Settings → Plugins → 齿轮 → Install Plugin from Disk` 中选择 ZIP，按提示重启；手动磁盘安装不需要先解压 ZIP。自动安装与手动安装应使用同一组固定版本。

## 必要设置

独立 SDK 配置完成后，在 IDEA 中检查：

1. **项目 JDK**：在 Project Structure 中添加并选择实际 `JAVA_HOME` 指向的 JDK 8。默认下载外层目录是 `~/.local/share/java-dev/jdk8`，真实 JDK Home 可能位于其内部 `Contents/Home`；复用已有 JDK 时路径也可能不同。
2. **Gradle 分发**：在 Gradle 设置中选择本地 Gradle 安装，目录填实际 `GRADLE_HOME`，默认 `~/.local/share/java-dev/gradle-4.5.1`，与工具验证的版本一致。
3. **Gradle JVM**：选择同一个 JDK 8。IDEA 自带运行时用于 IDE 本身，不等于项目或 Gradle 的 JDK。
4. **注解处理**：项目使用 Lombok 且由 IDEA 编译时，按项目要求启用 annotation processing；Gradle 构建中的处理器依赖仍由业务项目维护。
5. **项目导入与功能**：导入真实业务项目，核对依赖仓库、运行配置、数据库连接及插件实际功能。

默认修复和构建验证直接调用 `$GRADLE_HOME/bin/gradle`，不依赖项目 Wrapper。若团队明确要求使用 Wrapper，可由维护者保留并手动配置；不要把其缓存路径当作当前独立 Gradle 的 `GRADLE_HOME`。

终端环境和 IDEA 设置需要分别确认。查看已生成变量可在新终端运行：

```bash
source "$HOME/.config/java-dev/env.sh"
printf '%s\n' "$JAVA_HOME" "$JAVA_8_HOME" "$JRE_HOME" "$GRADLE_HOME" "$GRADLE_4_5_1_HOME"
```

自定义过 `ENV_FILE` 时使用实际文件。IDEA 安装成功、插件安装验证通过和 SDK 版本通过，都不能替代项目构建；先菜单 `3` 选项目，再菜单 `1` 完成整体修复和构建，或使用[独立构建验证入口](gradle.md#维护者命令行)。

## 历史与其他资源

每次修复开始后，成功或失败均记录到 `~/Library/Logs/team-java-env/history/<本次记录>/`。`report.md` 汇总步骤，`steps.tsv` / `result.tsv` 记录状态，`config-changes.diff` 展示配置差异；插件阶段有逐项结果与必要的 `plugin-backups/`。菜单 `10` 查看历史，`--dry-run` 不创建历史。

DBeaver 仍由菜单 `6` 下载 DMG 后手动安装。Database Navigator 或 DBeaver 首次连接数据库可能需要额外 JDBC 驱动；业务依赖、驱动、数据库连接和 MySQL 镜像不因 IDEA 安装完成而自动准备好。
