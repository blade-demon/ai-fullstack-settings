# Go 终端界面

成员交互入口已迁移到 Go + Bubble Tea。界面包含 Java 环境、Gradle 版本、前端工具和安全卸载页面；使用方向键选择，Enter 查看并确认操作，Esc 返回。执行页显示明确的阶段状态与可滚动日志，不用等待时间伪造百分比。

## 入口与操作

| 入口 | 有交互终端时的默认行为 |
| --- | --- |
| `开始配置.command` | 打开主界面，先做 Java 只读检查 |
| `开始配置.command --frontend` | 打开前端工具页面 |
| `卸载环境.command` | 打开安全卸载页面，不运行已安装 SDK 做扫描 |
| `npx` 包的 `install` / `frontend` / `uninstall` | 使用同一个下载入口，分别打开上述页面 |

- 菜单：↑↓ / j、k 选择，Enter 继续，Esc 返回，q 退出。
- 确认页：Enter 确认后才启动操作，Esc 返回。
- 执行页：↑↓、PgUp、PgDn 滚动日志，End 跟随输出；Esc 取消并等待任务退出，Ctrl+C 取消后退出界面。
- 结果页：显示成功、失败或取消；失败时显示真实退出码，Enter / Esc 返回菜单。后台任务和卸载预览的完整日志保存在 `~/Library/Logs/team-java-env/tui/`。
- 窗口不足 52 列 × 16 行时提示扩大窗口，并禁止不可见的确认操作。

取消会处理整个后台进程组，先请求中断，必要时逐步终止并等待后代退出。已经完成的安装保留，不承诺自动回滚全部组件。Go 程序在后台任务期间收到 HUP、TERM、INT，会完成清理后返回 129、143、130，不能将中断报告为成功。交互卸载期间，Ctrl+C 交给卸载器处理后返回结果页。自动化终止 npx 会话应使用 TERM；不要仅向处于交互保活状态的包装层 PID 发送 INT。

卸载页面提供只读预览。进入实际卸载时，界面暂时把终端交给现有卸载器，让使用者选择 IDEA 范围、查看准确计划并输入 `DELETE`，结束后返回 TUI 结果页。交互卸载的终端输出不另存为 TUI 日志；实际执行清理时，卸载器将计划、操作及结果写入 `~/Library/Logs/team-java-env/cleanup/<本次记录>/report.txt`，在确认前取消或无清理内容时不产生该记录。TUI 不附加 `--apply --yes`；当前前端工具仍不在 Java 卸载范围。

IDEA 与 iTerm2 的菜单及确认页显示当前 `HOME` 展开的个人 Applications 目录，例如 `/Users/用户名/Applications`。实际安装脚本使用同一规则；不在主目录下重复添加 `Users/用户名`。

## 普通命令行模式

`--plain` 使用原来的文本菜单或命令行。已有明确参数保持兼容，不会被强制放进 TUI：

```bash
bash 开始配置.command --plain
bash 开始配置.command --frontend --component node --node-version 18
bash 卸载环境.command --plain
bash 卸载环境.command --dry-run
```

无 TTY 的流水线应传入明确操作参数。Go 程序本身在无 TTY 时会提示而非等待键盘；原非交互卸载默认仍仅预览。本次迁移也修复了 npx 和下载模板的终端取消处理，因此需重新 `npm pack` 并分发新包，同时让双击入口用户重新下载 `start.zip`。之后仅修改 TUI 或 Bash 执行层时，可只更新服务器的完整工具包；临时 npm 包仍未公开发布。

## 构建与分发

Windows 或 macOS 下载服务器正常拉取仓库后，使用原来的 `python3 server/manage.py start` 即可，Windows 使用 `py -3`。有效本地产物会复用；缺失、损坏或过期时，根据 `resources/runtime-lock.json` 自动下载匹配的界面和卸载运行文件。首次缺少文件需访问 GitHub Release 或镜像，有效缓存可离线复用；下载服务器和成员都无需安装 Go，也无需手动复制四个文件。

以下构建步骤供修改界面源码的维护者使用。界面源码位于 `tui/`，锁定 Bubble Tea、Bubbles、Lip Gloss 及间接依赖，使用 Go 1.27.1 构建。构建工具设置 `CGO_ENABLED=0`，分别生成 macOS arm64 和 amd64 可执行文件，并收集 Go 和依赖的许可证。

```bash
python3 tools/build-tui.py --go /absolute/path/to/go
python3 tools/build-tui.py --verify-only
```

默认产物：

```text
resources/tui/
├── team-dev-env-arm64
├── team-dev-env-amd64
├── manifest.json
└── THIRD_PARTY_NOTICES.txt
```

构建使用临时缓存，不要求将 Go 放入用户全局 PATH；`--verify-only` 只读校验，无需 Go。每次 Go 源码、测试或依赖锁变化后须重建。维护者在 Mac 上同时确认卸载产物有效，运行 `tools/release-runtimes.py` 生成确定性 ZIP 与锁文件，上传匹配的 GitHub Release，并将锁与源码配套提交。服务器随后自动获取成品，打包到 `.support/tui/`，在 Windows 上只校验文件，不运行 Mac 程序。发布命令、镜像和离线准备见[运行文件发布指南](runtime-release.md)；目前没有 CI 自动构建或上传。

`python3 server/manage.py prepare-runtimes` 可单独补齐运行文件，`--offline` 仅校验本地且不写入。`package` 仍只校验和打包，文件过期或损坏时失败；不会隐式编译或联网。仅在预备离线服务器时，可把已校验的 TUI 和卸载七文件按原目录一起复制过去，再执行离线校验。

拉取源码不会更新 `dist/server`。正式发布需重新完成 `start`，以输出的 `go-tui-<实际 TAR 摘要前 12 位>` 和 `/release.json` 核对当前服务；端口占用导致启动退出时，旧服务可能仍提供旧界面。

成员入口按 CPU 架构选取程序，并重新校验摘要。若界面组件缺失或损坏，应重新下载完整包；明确需要使用旧文本模式时加 `--plain`。卸载运行包及原有资源准备流程见[卸载说明](cleanup.md)和[分发指南](../distribution.md)。

安装执行层仍是已有 Bash 脚本；阶段信息通过显式协议传给 TUI，最终状态由实际退出码决定。日志里的终端控制序列不会直接写入界面，内存日志和阶段列表有上限，后台任务的完整日志保存在磁盘。
