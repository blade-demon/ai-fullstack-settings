# 自动补齐运行文件与发布版本验证实施计划

> For agentic workers: use subagent-driven-development with independent module ownership and a final integration review.

**目标：** Windows/macOS 下载服务器更新源码后执行一键启动，即可自动获得与当前源码匹配的 Go TUI 和卸载器，无需手工传运行 ZIP，并能确认实际发布版本。

**架构：** 源码提交 resources/runtime-lock.json 固定运行 ZIP 的来源、摘要、大小、7个成员及两个源码摘要。现有有效产物优先复用；缺失或失效时仅下载和验证，不在服务器执行 Mac 程序。维护者工具生成确定性 ZIP 与锁文件，托管于现有 GitHub Releases；可显式指定内网镜像。发布目录生成 release.json，启动输出与 HTTP 下载均可核验版本。

**技术：** Python 3.8+ 标准库；成员程序仍为已有 Go 与冻结卸载器，业务安装功能保持不变。

## 约束与接口

- 不依赖服务器 Go、macOS 或额外 Python 包。Windows 不构建/执行 Mac 程序。
- ensure_runtimes(root, base_url=None, offline=False, report=print) 返回 release、downloaded、source_sha256；有效本地文件无需 lock 或网络。
- 缺失/失效时读取 resources/runtime-lock.json，下载前核对当前源码；ZIP和精确7成员分别校验摘要、大小及原有Mach-O/源码/许可契约。
- 不接受路径逃逸、链接、重名或多余ZIP成员；校验完成后只替换受管7文件，失败回滚，保留未知文件与旧发布包。
- start/preview 在占用端口成功后、SDK下载前补齐运行文件；prepare-runtimes 提供单独准备与离线验证。package 继续只校验/打包，不隐式联网。
- 默认 GitHub Release URL 由锁文件固定；--runtime-base-url 或配置 runtime_base_url 可指定内网目录，不绕过校验。
- release.json 包含 schema、interface=go-tui、真实bundle SHA-256、两个源码摘要及发布时间；版本由实际bundle摘要得出，不能把源码更新误报为已发布。
- serve 拒绝没有新版发布信息或摘要不一致的旧包；下载入口与发布信息返回禁止缓存的响应头。
- 保留端口占用时不改现有服务/发布物的行为，但清楚提示本次没有更新安装包。
- 既有源码/产物验证、DELETE确认、应用安装目录、前端安装及npx行为不变。

## 任务

- [x] runtime_fetch：运行文件校验、获取、事务发布与离线/恶意包/回滚测试。
- [x] runtime_release：确定性运行ZIP、lock/许可/来源清单及生成器测试。
- [x] root：一键启动、prepare-runtimes、mirror/offline参数、版本元数据与HTTP校验、占用端口提示和集成测试。
- [x] root：更新首次部署/更新文档，说明本地源码与实际发布版本的区别。
- [x] review：独立复查，完整回归，删除运行文件后的真实冷启动验证。
- [x] release：生成并发布首次匹配运行包，验证公开下载摘要；确认代码与锁文件可供服务器更新。

执行环境沿用当前共享项目目录与已验证构建产物；不创建额外工作树，不停止未知服务，不直接修改 192.168.0.101 上的文件。

验证记录：完整 34 模块共 537 项回归通过；补充 BOM + 大写摘要 package/serve 用例通过；Python 3.8 语法检查通过。独立复查发现的自定义仓库 URL 和 BOM 兼容两项问题均已修复并复查通过。

首次运行文件已发布：https://github.com/blade-demon/ai-fullstack-settings/releases/tag/runtimes-37f4ae609031d1cf ，ZIP SHA-256 为 `37f4ae609031d1cffd2db76ddfad002b99a60abfe484896320d1e7a8bfc3414b`。全新临时检出（无运行文件、PATH 无 Go）已通过公开 Release 冷下载 → start 打包 → HTTP release.json/启动ZIP/工具包校验 → 真实 Go TUI 打开并退出；未安装或卸载用户软件。192.168.0.101 仍需由维护者拉取本次改动并重新 start，不会远程替用户关闭现有服务。
