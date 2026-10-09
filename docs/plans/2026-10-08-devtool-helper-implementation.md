# devtool-helper 实施计划

状态：2026-10-09 已实施并完成本地隔离验收；658 项完整回归、Go 全套、真实 SDK 切换及 HTTP/终端验证通过。详见[验证记录](../verification.md#2026-10-09统一-helper-交付与六组件管理)。

目标：实现已确认设计中的统一入口、三个发布文件、六组件安装/卸载、版本切换及真实进度。

设计依据：[统一交付入口设计](2026-10-08-devtool-helper-design.md)。在 `codex/devtool-helper` 分支实施；过程记录与审查材料保存在系统临时目录，不进入发布包。

## 固定约束与接口

- 成员为 macOS，自带 Bash 3.2，不能要求 Python/Node/Go；维护者 Python 3.8+，服务端不执行 Mac 二进制。
- 公共动作只有 install/uninstall/help；组件为 jdk,gradle,nvm,idea,iterm2,oh-my-zsh；安装顺序 jdk,gradle,nvm,iterm2,oh-my-zsh,idea。
- `run-tool.sh install|uninstall [参数]` 是 TAR 唯一内部入口；TTY 安装 Enter 直接执行，删除需要原 DELETE 确认。
- `manage-components.sh --plan-json --components CSV --gradle-version 4.5.1|6.8|all --node-version none|10|14|18|22|all` 只生成计划；普通调用执行，`--dry-run` 只预演。新增默认规则：安装页、一键全部及省略 --node-version 时选择并安装14.21.3；其他单版/none/all 仍可选。显式 all 才安装四版，首次或旧 default 失效时回退到14，有效 default 保留；单版（包括默认单14）设所选默认，none 不改默认。
- Go CLI 使用 `--page home|install|cleanup --components CSV --gradle-version VERSION --node-version VERSION` 传入预选。
- `release.json` schema=2，launcher/bundle 均为 path,size,sha256 对象；成员发布仅 helper、TAR、release.json。
- 新组件进度协议沿用 `@@TEAM_TUI`：`plan\tcomponents\tCOUNT\tTITLE`、`component\tID\tSTATUS\tTITLE`；stage 保持兼容。下载事件为 `progress\tCOMPONENT\tRESOURCE\tATTEMPT\tCOMPLETED\tTOTAL`，未知 TOTAL 为 0。所有字段需校验、清洗。
- 不执行真实用户安装/卸载。测试用临时 HOME、测试服务和模拟 SDK。构建后只运行帮助、预演和只读校验。

## Task 1 发布与统一下载器

涉及 server/manage.py、server/publication.py、tools/devtool-helper.sh.in、tools/package-files.txt、npm-cli、tools/release-runtimes.py 和对应测试。

- [x] 先修改分发/服务端用例，观察旧代码不满足三个文件、schema 2、统一入口及 HTTP 范围。
- [x] 实现 launcher/bundle 清单与 helper 校验；旧五项产物退场。
- [x] 资源只读映射、显式部署副本和默认临时预览；运行文件发布按需精简。
- [x] npm 移除 frontend，复用 helper 模板及明确动作。
- [x] 运行 `python3 -m unittest discover -s tests -p 'test_distribution.py'` 及 server/npm/runtime_release 测试；审查分发和路径安全。

## Task 2 组件计划与版本配置

涉及 manage-components.sh、run-tool.sh、run-tui.sh、managed-env.sh、install-node.sh、frontend-env.sh、安装叶子脚本与组件/版本测试。

- [x] 写固定顺序、依赖去重、无 TTY 约束和 nvm-only 的失败测试。
- [x] 安装/卸载入口合并，删除旧数字菜单和 .command；实现统一结构化计划和顺序队列。
- [x] Gradle 自动生成 gradle_use，登记与默认激活分离；Bash/Zsh 同进程切换测试。
- [x] Node 支持 10/14/18/22/none/all，补齐固定资源与 nvm 切换指引，保留既有版本。
- 2026-10-09 追加要求：默认选择/安装与 all 首次或失效回退改为14；本轮实现和验收记录由主任务追加，不改写原验证历史。
- [x] 安装完成报告显示实际版本和加载/切换方法；组件、版本、归属与已有安装流程回归。

## Task 3 六组件卸载

涉及 tools/uninstall_java_gradle.py、前端来源记录和卸载测试。

- [x] 写组件隔离、实例白名单、独立配置、前端归属和默认引用清理的失败测试。
- [x] Cleaner 在扫描前约束 components，新增前端计划和来源验证。
- [x] 预览提供结构化实例，执行复核选择；保留 DELETE、无 TTY 默认预览、取消及进程安全。
- [x] iTerm2 收据绑定实际对象；保留用户 nvm/Oh My Zsh 内容和宿主终端。
- [x] 运行全部卸载与配置/归属测试并审查删除边界。

## Task 4 TUI 选择与进度

涉及 tui/*.go、common.sh、下载进度公共模块、三个实际下载路径及事件测试。

- [x] 写六组件选择/Enter 执行、版本选项、固定总量/失败不补齐和新旧事件解析的失败测试。
- [x] 实现单一安装页、卸载组件/实例选择，使用统一计划及执行层。
- [x] 实现总组件条与确定/不确定阶段条；事件节流并保留终态。
- [x] 接入下载真实字节；结果页展示成功组件的版本切换指南。
- [x] 执行 Go 测试和伪终端/事件回归，复核小窗口和取消。

## Task 5 集成与交付验证

- [x] 完整隔离 Python/Go 回归，Bash 3.2 语法及文档引用检查。
- [x] 更新当前有效文档，历史记录保留；移除旧入口说明。
- [x] 重建双架构 TUI 与 universal2 cleanup，生成必要 manifest/锁，按新规则打包三个成员文件。
- [x] 实际 HTTP 下载、校验、帮助与只读预演，验证临时目录和产物数量。
- [x] 独立审查并处理问题，记录实际验收和发布限制；不把本地构建报告为已部署远端。
