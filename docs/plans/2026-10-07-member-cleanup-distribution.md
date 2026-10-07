# 成员卸载工具分发实施计划

目标：按已确认方案，在 start.zip 中同时提供「开始配置.command」「卸载环境.command」。两入口复用同一最新工具包的下载、SHA-256 校验与安全解压；完整工具包也提供两个入口。成员卸载无需安装 Python，安装菜单保持不变。

架构：卸载实现仍以 tools/uninstall_java_gradle.py 为唯一源码，在 macOS 上用 PyInstaller 生成包含 arm64 / x86_64 的 universal2 命令行工具。构建产物位于 resources/cleanup/，服务端仅校验和打包，在 Windows 上不编译或执行它。成员入口只负责启动打包工具、保留终端结果，不增加删除范围或绕过 DELETE 确认。

固定接口：

- 构建：tools/build-cleanup.py；默认输出 resources/cleanup/cleanup-macos-universal2、manifest.json、THIRD_PARTY_NOTICES.txt。
- manifest：schema=1、sha256（可执行文件）、source_sha256（原 Python 源码）、architectures=[arm64,x86_64]，以及构建工具/Python 版本；打包器检查摘要、源码一致性和 Mach-O 架构。
- 分发路径：.support/cleanup/cleanup-macos、manifest.json、THIRD_PARTY_NOTICES.txt；可执行权限 0755。
- 启动模板增加 @ENTRY_NAME@ 与 @ENTRY_LABEL@，生成 start.command / uninstall.command；两个入口仅改变完整包中的目标文件名。
- 卸载入口：dev-kit/卸载环境.command；无参数交互保留原程序的预览、IDEA 范围选择、DELETE 确认；非交互保持默认预览；双击后保留结果等待回车。

任务：

- [x] 构建工具与 universal2 实际产物：隔离构建依赖，记录源摘要和第三方许可，只运行 help / 空临时 HOME 预览。
- [x] 分发器与双启动入口：更新白名单、执行权限、产物缺失/损坏/过期校验；测试两个入口目标与参数、更新下载、失败不发布。
- [x] 成员卸载入口：测试无 Python PATH、取消、参数传递和状态保留；保留原删除实现与来源标记边界。
- [x] 更新成员/维护者说明，构建可下载 ZIP，运行完整回归、真实打包产物安全预览与独立复查。

验证不得卸载真实机器的软件或配置。生成本地发布包不代表已上传或替换团队线上服务。保留现有全部安装菜单与 Gradle 两版本逻辑，不创建 Git 提交。

验证记录：407 项完整回归通过；真实 universal2 的 arm64 / x86_64（Rosetta）help 与安全预览通过，空 PATH 无需外部 Python。实际启动 ZIP 的 HTTP 下载、工具包校验、解压与模拟 SDK 预览通过。生成 dist/member-cleanup-preview/（本机 127.0.0.1:8080 地址），未上传或替换团队线上服务。构建发布回滚故障测试及独立复查通过。
