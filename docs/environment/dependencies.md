# 项目依赖

Lombok、Spring、MySQL Connector/J 和 MyBatis 等依赖由真实业务项目的 `build.gradle` 及团队依赖仓库管理，不属于系统安装包。成员组件安装配置 SDK/工具和六个 IDEA 插件，维护者底层脚本还可配置 Wrapper 下载地址、检查并构建明确指定的项目；这些操作不修改业务依赖。IDEA Lombok 插件与项目 Lombok 库分别管理。

六组件全量预检还要求所选资源、可用 Git（Oh My Zsh）、macOS 13+（iTerm2）及 Apple Silicon 的 Rosetta（Node 10/14）等前提。缺失或冲突时保留选择并说明原因，不执行或静默跳过所选组件。全量顺序为 JDK → Gradle → nvm/Node → iTerm2 → Oh My Zsh → IDEA/插件；Gradle 补入 JDK，IDEA 不隐式安装 JDK。

导入项目前请确认：

- 项目使用团队约定的 Gradle 版本；一键安装基线为 4.5.1，6.8 需按项目要求单独选择。使用 Wrapper 时应提供完整 Wrapper，安装新 SDK 不会自动升级项目配置。
- Spring / Spring Boot、Lombok、MyBatis 和数据库驱动版本符合 JDK 8 与现有项目要求。
- 能访问项目声明的依赖仓库；Gradle 分发包服务器仅提供 Gradle 本体，不自动代理 Maven 依赖。
- 数据库连接配置指向实际开发库，驱动与服务端版本匹配。

## Gradle 4.5.1 与 Lombok

原指南中的 `annotationProcessor 'org.projectlombok:lombok:1.18.xx'` 不能直接使用：`1.18.xx` 不是可解析版本，`annotationProcessor` 内置配置则从 Gradle 4.6 才引入。[Gradle 4.6 官方说明](https://docs.gradle.org/4.6/release-notes.html#convenient-declaration-of-annotation-processor-dependencies)

保持 Gradle 4.5.1 时，沿用项目已经验证的 Lombok 版本及处理器配置；如需新增，由项目维护者确认与现有 Java 插件和构建任务的兼容性。不要直接复制新版本 Gradle 示例，也不要为适配示例擅自升级项目构建工具。

环境配置完成后，在实际项目中执行约定的编译与测试任务，确认命令行构建和 IDEA 使用同一套 JDK 与依赖配置。
