# 提前准备内网分发资源

用户确认 JDK 1.8、Gradle 4.5.1，安装包统一放在项目 `resources/`。面向 macOS Intel 与 Apple Silicon，固定版本而非 latest。

## 目录与行为

- `resources/catalog.tsv`：官方固定 URL、版本、架构、相对路径和上游 SHA-256；插件无上游 SHA 时标记 `-`，首次下载记录本地摘要。
- `resources/runtime/`：JDK、Gradle；`resources/software/`：IDEA 社区版、DBeaver；`resources/plugins/`：与 IDEA 2024 build 匹配的免费插件。
- `tools/prepare-resources.sh`：下载、校验、复用；支持选择分类、架构和条目。只下载文件，不运行安装程序。
- `tools/package.sh --with-resources`：校验资源后把资源单独放到发布目录的 `resources/`，软件大包不塞进启动包。成员工具只收录校验通过的下载清单。
- 成员菜单增加下载软件/插件入口，按本机架构展示，从内网下载到用户 Downloads 文件夹；IDEA 插件从磁盘安装。
- 运行时安装路径改为 `resources/runtime/`，默认服务器继续为 `127.0.0.1:8080`。

## 验收

- [x] 官方来源、版本、静态兼容性核对。
- [x] 下载脚本先失败后通过的隔离测试。
- [x] 实际下载核心运行时、两架构开发软件和适配插件到 `resources/`，保存并复验校验和。
- [x] 打包只发布清单内校验通过文件，支持非默认输出目录，保留未知文件。
- [x] 成员内网下载入口及现有运行时流程回归。
- [x] 文档更新，区分预下载、软件安装、插件运行验收与项目依赖缓存。

## 实际验收结果

- 2026-10-06 已准备10个资源文件，共2,527,521,456字节（2.53GB）。7个运行时/软件包与官方SHA-256一致；3个插件从官方Marketplace取得并保存本地SHA-256记录。
- 全部72项隔离测试通过；14个脚本/模板语法与Markdown本地链接检查通过。
- 已生成dist/server完整发布目录；实际用回环HTTP下载发布物中的MyBatisX并核对SHA，验证外部项目Wrapper写入官方Gradle摘要。未安装软件/插件或发布真实服务器。
- 默认服务器仍为127.0.0.1:8080；正式部署前通过--server重新打包。Docker、收费SpringBootHelper、不兼容的旧SpringAssistant、业务依赖和容器镜像不在默认资源包内。
