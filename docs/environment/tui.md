# Go 终端界面

成员运行 `bash devtool-helper.sh` 打开 Go + Bubble Tea 首页；`install` / `uninstall` 直接进入同一安装页或六组件卸载页。npm 薄入口也只有 install/uninstall。交互统一使用 TUI，frontend 独立页面、数字菜单和 --plain 已移除。

## 选择、执行与结果

首页有“安装与配置”“卸载工具”“一键安装配置全部”。安装页与卸载页均展示 JDK、Gradle、nvm、IDEA、iTerm2、Oh My Zsh；方向键移动、空格勾选，安装页左右键切换版本。参数化组件和版本会预选到同一页面。

**安装页 Enter 直接预检并执行**，没有额外计划确认页。空选择不执行；当前页显示默认版本、目录、依赖补入及持久默认变化。预检失败保留选择并显示原因，不执行任何组件，也不静默省略选中项。一键全部按 Enter 连续执行 JDK 8 → Gradle 4.5.1 → nvm/Node 14.21.3 → iTerm2 → Oh My Zsh → IDEA/六个插件；安装页的 Node 默认选择14；其他单版或 all 仍可用左右键选择，显式 all 才安装四版。all 首次或旧 default 失效时回退到14，有效 default 保留；单版（包括默认单14）设所选默认，none 不改默认。部分选择及自动补入 JDK 依赖同样遵循相对顺序。

卸载默认全不选，只静态扫描文件及来源，不运行 SDK。先选择组件和实例，Enter 进入所选范围的清单与 `DELETE` 确认；不是快捷全卸载。删除和配置范围由执行层过滤，IDEA 用户数据可保留。TUI 不自动附加 --apply/--yes，详细边界见[卸载指南](cleanup.md)。

执行页显示总组件条和当前阶段条：总进度按固定计划中验证完成的组件计算，Node 版本及插件是对应组件子任务。可信总大小的下载显示实际字节与百分比，未知大小或安装/配置阶段显示动态条；下载 100% 不代表组件完成。失败、依赖跳过、取消及待处理不计作完成，独立组件可继续，取消停止余下任务。

- 执行页：↑↓、PgUp、PgDn 滚动日志，End 跟随；Esc 取消并等待任务退出，Ctrl+C 取消后退出。
- 结果页：显示实际状态、失败退出码、日志和报告位置，Enter/Esc 返回。成功或复用后列出实际版本、有效默认、实际加载命令及 `gradle_use` / `nvm use` 指引，未安装版本不显示为可用。
- 窗口过小会提示放大并禁止不可见的选择或确认。界面缺失/损坏须重新下载，不能退回旧文本菜单。

helper/TUI 不能改变父终端环境；“已写好新终端默认”与“验证进程已通过”不表示原终端已切换。新开终端或使用结果中的加载命令后，再切换已安装版本。只安装 nvm 时显示“本次未安装 Node”，按实际已有状态提供 nvm ls 与默认值。

取消处理后台进程组并等待退出，已完成安装保留。HUP/TERM/INT 退出为 129/143/130；交互卸载期间 Ctrl+C 交给卸载器后返回结果页。自动化终止 npx 会话使用 TERM，不只向交互保活包装 PID 发 INT。普通 CLI 不显示内部事件协议。

TUI 完整日志保存在 `~/Library/Logs/team-java-env/tui/`，统一组件记录位于同一根目录的 `components/`；实际卸载在 `cleanup/<本次记录>/report.txt` 写计划和操作结果，确认前取消不创建清理记录。交互卸载终端输出不另存 TUI 日志。

## 参数化 CLI

```bash
bash devtool-helper.sh help install
bash devtool-helper.sh --dry-run install --components all
bash devtool-helper.sh install --components gradle --gradle-version all --dry-run
bash devtool-helper.sh uninstall --components nvm,iterm2 --dry-run
```

本地 help 和动作前全局 --dry-run 不联网；动作后的 --help/--dry-run 下载工具后到业务执行层。无 TTY 的实际安装必须明确组件；非交互默认卸载只预览，真删要求明确 --components 加 --apply --yes。公共入口不接受底层 repair-env.sh 的 --project/--scope。

## 构建与分发

Windows/macOS 下载服务器使用 Python 3.8+ 的 `start`，优先复用有效的 `resources/tui/` / `resources/cleanup/`，缺失/损坏/过期时根据 runtime-lock 自动获取匹配运行文件；服务器和成员无需 Go，Windows 不执行 Mac 程序。

修改界面源码的维护者使用 Go 1.27.1，锁定 Bubble Tea、Bubbles、Lip Gloss 与间接依赖；构建工具设置 CGO_ENABLED=0，生成 darwin arm64/amd64，并收集许可证：

```bash
python3 tools/build-tui.py --go /absolute/path/to/go
python3 tools/build-tui.py --verify-only
```

产物为 `resources/tui/{team-dev-env-arm64,team-dev-env-amd64,manifest.json,THIRD_PARTY_NOTICES.txt}`。构建使用临时缓存，verify-only 只读无需 Go；源码、测试或依赖锁变化须重建。卸载工具另为 universal2。维护者显式生成一个运行文件 ZIP 与 schema 1 锁，上传配套 Release；常规成员发布则只有 helper、TAR、schema 2 release.json。完整步骤见[运行文件发布指南](runtime-release.md)。

`prepare-runtimes --offline` 只校验且不写入；`package` 只校验和打包，不隐式联网/编译。`git pull` 不更新服务，重新 start 并核对实际发布版本；端口占用退出时旧界面仍可能被托管。成员运行前按架构选择程序并检查摘要、manifest 和许可。当前文档不等于运行文件 Release 已上传或实机交互验收已通过。
