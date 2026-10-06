# 独立安装 Gradle 4.5.1 与验证项目构建

默认方案是在用户目录安装独立 Gradle 4.5.1，配置完整环境变量，再用这个明确的版本验证项目。**不再把 Wrapper 缓存视为独立安装，也不以 `--version` 成功代替构建成功。**

成员可使用菜单 `1` 一键修复全部环境，或菜单 `7` 单独修复 Gradle。先用菜单 `3` 选中项目时，菜单 `7` 完成安装验证后必须实际构建；没有项目也能安装 Gradle，但结果明确为“未执行构建”。

## 安装位置与环境变量

| 项目 | 默认值 |
| --- | --- |
| `GRADLE_INSTALL_DIR` | `~/.local/share/java-dev/gradle-4.5.1` |
| `GRADLE_HOME` | 已验证的实际独立安装目录 |
| `GRADLE_4_5_1_HOME` | 团队 4.5.1 基线下与 `GRADLE_HOME` 相同 |
| `GRADLE_USER_HOME` | `~/.gradle`，用于 Gradle 用户配置、依赖等缓存 |
| `PATH` | 优先使用 `$JAVA_HOME/bin` 和 `$GRADLE_HOME/bin`，重复项去重 |

安装目录和缓存目录用途不同：Gradle 程序放在 `GRADLE_HOME`，不是放在 `~/.gradle/wrapper/dists`。以后若手动使用项目 Wrapper，它仍可能另建自己的分发缓存；那不改变本工具默认使用独立 Gradle 的规则。

变量写入 `${ENV_FILE%/*}/gradle.sh`，默认由 `~/.config/java-dev/env.sh` 聚合加载；完整 JDK 变量也一并检查和配置。环境文件、Shell 入口、首次备份和幂等规则见[运行环境指南](runtime.md#三个受管环境文件)。

## 安装前准备

- 已有完整 **JDK 8**，包括可运行的 `java`、`javac` 与实际 `jre` 目录。缺少时先用菜单 `2`；一键修复会先处理 JDK。
- 团队内网服务可以提供 Gradle ZIP，成员清单中具有对应固定 SHA-256。新的独立安装不接受没有固定摘要的下载。
- 要验证构建时，准备真实业务项目，其根目录包含 `build.gradle` 或 `build.gradle.kts`。**不要求存在 `gradlew` 或 Wrapper JAR。**

Gradle 安装包不包含项目的 Maven 依赖、Gradle 插件和企业仓库凭据。项目构建可能仍需访问团队依赖仓库；文件已经下载到电脑，不代表所有业务依赖已满足。

## 修复过程与成功标准

1. 检查已有 JDK 8、目标目录及配置路径。未知或不完整的已有 Gradle 安装目录会保留并报错，不直接覆盖。
2. 已有完整同版分发时，实际运行其 `bin/gradle --version` 核对版本后复用。缺少时从内网下载固定 ZIP，校验 SHA-256、归档路径和分发结构，验证版本后保存到用户目录。
3. 写入完整 JDK/Gradle 环境模块，加载验证变量和 Java/Gradle 命令路径；只显示“复制完成”不算这一步成功。
4. 未选择项目时，报告 SDK 安装及环境验证结果，并明确未构建。选择项目时，进入该目录调用目标 `$GRADLE_HOME/bin/gradle`，执行：

   ```bash
   "$GRADLE_HOME/bin/gradle" --no-daemon --console=plain build
   ```

5. 构建同时满足**退出码为零**、输出含 **`BUILD SUCCESSFUL`**，才报告项目构建验证通过。非零退出码按原值返回；即使退出零，没有成功标记也算失败。

默认 `build` 不添加跳过测试的参数。它会执行项目定义的编译、测试及相关任务，可能更新项目的 `build/` 和 Gradle 缓存。维护者确有需要时，可通过 `GRADLE_BUILD_TASK` 指定一个任务，如 `:service:build`；不能传入多个任务、命令行选项、空白或 Shell 命令。改变任务后，以报告记录的实际任务为准，不能把局部任务通过说成完整默认构建通过。

## 成员操作

1. 打开「开始配置.command」，查看扫描结果。JDK 不完整时先选菜单 `2`，或直接用菜单 `1` 修复全部环境。
2. 有项目时用菜单 `3` 选择项目，再选菜单 `7`；没有项目时可直接用菜单 `7` 安装和验证 SDK。
3. 等待版本、环境和实际构建结果。构建失败时保留输出，不要通过删除校验、跳过测试或换成其他 Gradle 命令来掩盖失败。
4. 用菜单 `10` 查看本次历史的 `report.md`、`steps.tsv`、`result.tsv` 和构建日志。SDK 已安装但构建失败时，整体结果仍是失败。
5. 新开终端；在 IDEA 中选择同一个 JDK 8 和本地 Gradle 目录，见 [IDE 设置](ide.md#必要设置)。

## 维护者命令行

以下命令在本工具仓库根目录执行。正式下载应使用已配置团队地址、固定摘要清单的工具包；直接调试源码时，维护者也可显式提供 `GRADLE_SHA256`。

```bash
# 只预览：不加载生成的环境、不执行 SDK、不下载或构建
bash dev-kit/.support/scripts/runtime/install-gradle.sh --project "/absolute/path/to/java-project" --dry-run

# 没有项目：安装/复用独立 Gradle，补齐环境并验证版本
bash dev-kit/.support/scripts/runtime/install-gradle.sh

# 有项目：安装/复用后强制真实构建验证，不要求 Wrapper
bash dev-kit/.support/scripts/runtime/install-gradle.sh --project "/absolute/path/to/java-project"

# SDK 已就绪时，单独验证业务项目
bash dev-kit/.support/scripts/runtime/verify-gradle.sh --project "/absolute/path/to/java-project"

# 需要完整修复历史时使用统一入口
bash dev-kit/.support/scripts/repair-env.sh --scope gradle --project "/absolute/path/to/java-project"
```

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

默认安装和验证不使用 `./gradlew`。项目的 Wrapper 文件仍可保留；团队需要手动维护其内网地址时，可运行：

```bash
bash dev-kit/.support/scripts/runtime/config-gradle.sh --project "/absolute/path/to/java-project" --dry-run
bash dev-kit/.support/scripts/runtime/config-gradle.sh --project "/absolute/path/to/java-project"
```

这个兼容配置脚本要求项目已有 `gradlew`、`gradle/wrapper/gradle-wrapper.jar` 和 `gradle-wrapper.properties`。它只更新分发地址、可取得的 SHA-256 和执行权限，首次修改保留 `gradle-wrapper.properties.bak`；不会替代独立安装或默认真实构建验证。

Wrapper 缓存与 URL、`distributionBase`、`distributionPath`、`zipStoreBase`、`zipStorePath` 有关。静态扫描发现 ZIP 不代表解压安装已完成；发现其他 URL 的同版本缓存也不等于当前项目缓存完整。无法可靠解析时会标为待确认，不改变独立 Gradle 的实际运行验证结果。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 缺少 JDK 8 或 `jre` | 用菜单 `2` 修复完整 JDK，再检查 `JAVA_HOME`、`JAVA_8_HOME`、`JRE_HOME` |
| 提示安装目录未知、不完整或版本不符 | 保留原目录，确认它的用途；另设用户安装目录或由维护者处理，不直接覆盖 |
| 提示缺少 SHA-256 | 使用维护者打包的最新成员清单，或由维护者提供已核验的固定摘要 |
| 下载出现 403/404 或连接失败 | 维护者检查服务和资源路径，见[服务启动指南](../service-startup.md) |
| SHA-256 不匹配或归档异常 | 停止安装，核对源包、清单与发布文件；不要关闭校验或只修改摘要 |
| 新终端仍使用旧版本 | 检查 Shell 加载入口、三个受管文件及 `PATH`；使用菜单 `10` 查看配置差异 |
| 版本验证通过，但项目构建失败 | 查看构建日志；检查业务代码、测试、依赖仓库、权限和项目版本要求，不能算作整体成功 |
| 退出零却提示缺少成功标记 | 输出未提供可确认的 Gradle 构建成功结果，按失败处理并交由维护者检查 |

修复历史默认在 `~/Library/Logs/team-java-env/history/<本次记录>/`，失败也保存。固定资源来源见[运行环境来源](../resources/runtime-sources.md)；本工具的隔离测试不等于已在真实业务项目完成构建，实际平台和项目组合仍应以本次验证结果为准。
