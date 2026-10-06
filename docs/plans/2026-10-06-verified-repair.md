# 可验证的一键环境修复与跨平台服务端

## 目标与成功标准

先扫描 JDK 8、Gradle 4.5.1、IDEA 及持久化环境配置，展示缺失项。修复后必须重新验证；选择项目时必须执行默认 `build` 任务（不跳过测试），仅当构建命令成功且构建结果确认成功，才将整次修复标记为成功。无项目时明确标记“环境验证完成，未执行项目构建”，不声称业务构建通过。

Mac 成员客户端保持 Bash 3.2 和系统工具方案，IDEA 位于 `~/Applications`。Windows 与 macOS 服务端使用 Python 标准库完成资源准备、打包与静态服务，不依赖 Bash、hdiutil 或系统 zip。

## 组件与接口

- SDK：JDK 持久化 `JAVA_HOME`、`JAVA_8_HOME`、`JRE_HOME`、`PATH`；Gradle 独立安装到 `~/.local/share/java-dev/gradle-4.5.1`，配置 `GRADLE_HOME`、`GRADLE_4_5_1_HOME`、`GRADLE_USER_HOME` 和 `PATH`。配置重入不重复追加，保留原配置备份。
- `scripts/runtime/install-gradle.sh [--project PATH] [--dry-run]`：验证本地 Gradle 4.5.1 与环境配置；指定项目后默认构建，不以 `--version` 代替构建。
- `scripts/runtime/verify-gradle.sh --project PATH [--dry-run]`：使用已验证的 JDK 8 和目标 Gradle，执行 `--no-daemon --console=plain build`；失败退出码透传。
- `scripts/software/install-idea-plugins.sh [--verify-only] [--dry-run]`：安装资源清单内全部五个插件，校验文件、插件 ID/版本和 IDE 兼容范围；保护未知目录，保存被替换的已知插件备份；不强制关闭 IDEA。
- `scripts/repair-env.sh [--scope all|jdk|gradle|idea|plugins] [--project PATH] [--dry-run]`：扫描→按需修复→验证→项目构建→审计总结。失败也保留变更和失败阶段，不能输出整体成功。
- `scripts/lib/audit.sh`：每次修复建立历史目录，保存前后状态、步骤退出码、日志、受管配置差异与备份，供开发者 review。
- `server/manage.py`：跨平台 prepare/package/serve，Windows `.cmd` 和 macOS `.command` 启动入口；只发布白名单文件，保持客户端 LF 与执行权限。

## 验收任务

- [x] 完整 SDK 环境写入、复用和失败测试。
- [x] Gradle 真正构建成功/失败控制最终状态，覆盖无 Wrapper 项目与路径空格。
- [x] IDEA 检测与全插件安装、升级备份、失败保护和验证。
- [x] 一键修复、前后审计、失败历史和菜单入口。
- [x] 跨平台服务端 prepare/package/serve 和原脚本兼容入口。
- [x] 整合回归、临时项目真实构建验证、发布物检查和文档。

验证结果：183 项回归通过，真实 SDK 编译成功与编译失败均控制最终状态，5 个真实插件完成临时安装与收据验证；最终分发包已重新生成并走通 HTTP 启动链路。Windows 实机验证未执行，详见[验证记录](../verification.md)。

## 边界

只运行用户明确选择的项目构建，不扫描或执行其他业务项目。IDEA 及插件验证需说明验证层级，不把文件复制等同于插件运行功能验收。不能因未选择项目就声称构建通过。保留原有用户配置和未知文件，不用关闭安全校验或删除全部缓存的方法处理失败。Windows 执行环境若不可用，明确区分跨平台代码测试与 Windows 实机验收。
