# 项目依赖

Lombok、Spring、MySQL Connector/J 和 MyBatis 等依赖由真实业务项目的 `build.gradle` 及团队依赖仓库管理，不属于系统安装包。本仓库脚本只配置 JDK 与 Wrapper 下载地址，不修改业务依赖。

导入项目前请确认：

- 项目提供完整 Gradle Wrapper，使用团队约定的 Gradle 4.5.1。
- Spring / Spring Boot、Lombok、MyBatis 和数据库驱动版本符合 JDK 8 与现有项目要求。
- 能访问项目声明的依赖仓库；Gradle 分发包服务器仅提供 Gradle 本体，不自动代理 Maven 依赖。
- 数据库连接配置指向实际开发库，驱动与服务端版本匹配。

## Gradle 4.5.1 与 Lombok

原指南中的 `annotationProcessor 'org.projectlombok:lombok:1.18.xx'` 不能直接使用：`1.18.xx` 不是可解析版本，`annotationProcessor` 内置配置则从 Gradle 4.6 才引入。[Gradle 4.6 官方说明](https://docs.gradle.org/4.6/release-notes.html#convenient-declaration-of-annotation-processor-dependencies)

保持 Gradle 4.5.1 时，沿用项目已经验证的 Lombok 版本及处理器配置；如需新增，由项目维护者确认与现有 Java 插件和构建任务的兼容性。不要直接复制新版本 Gradle 示例，也不要为适配示例擅自升级项目构建工具。

环境配置完成后，在实际项目中执行约定的编译与测试任务，确认命令行构建和 IDEA 使用同一套 JDK 与依赖配置。
