# 前端环境与 npx 入口实施计划

目标：在现有 macOS 工具中增加独立前端环境安装，包含 nvm、Node 14/16/18、iTerm2、Oh My Zsh 及 git、z、zsh-autosuggestions、zsh-syntax-highlighting。增加可用 npm pack 构建并通过 npx 运行的薄入口；使用者暂定临时包名，不执行公开发布。

已确认：原 Java 一键安装不加入前端工具；Oh My Zsh 采用上述四个推荐插件；npm 包先用临时名称。此次复用现有 Bash 安装逻辑，不把先前的 TUI 技术讨论当作已经选定框架。

约束：Node 14/16/18 为旧项目兼容版本，固定补丁版本；Node 14 在 Apple Silicon 上要求已有 Rosetta，不自动安装或接受许可；iTerm2 3.7.3 要求 macOS 13+。不覆盖用户已有安装或 shell 配置，不改变登录 shell、主题或字体。新资源统一固定 SHA-256，经内网资源服务下发；不执行远程 curl 管道安装脚本。测试仅使用临时 HOME。

- [x] 核对官方资源、固定版本/架构/摘要，扩展资源清单。
- [x] nvm/Node 模块：多版本安装、已有目录保护、默认版本与新终端加载、Rosetta 预检。
- [x] iTerm2 / Oh My Zsh 模块：应用验证、四插件安装/启用、配置备份与幂等。
- [x] 独立前端菜单及脚本调度：逐项记录退出码，失败不报告全部完成，原 Java 菜单保持行为。
- [x] npm 薄入口：临时名称 team-dev-env-preview，命令 team-dev-env；仅打包 Node 启动器与共用 Bash 下载模板，不包含私有服务器地址、SDK 大包或用户配置。显式 --server 或 SERVER_ADDR 指定团队服务，支持 install/frontend/uninstall。
- [x] 构建 npm tarball 并实际 npx 本地验证，更新说明，运行集成及完整回归、独立复查。

入口约定：`frontend-env.sh --component all|node|iterm2|zsh --node-version 14|16|18|all [--dry-run]`。前端单项脚本为 runtime/install-node.sh（--version）、software/install-iterm2.sh、software/install-zsh.sh。`开始配置.command --frontend ...` 与 npx 的 frontend 子命令均调用同一调度入口。

首次没有 Node 的机器继续使用双击入口；已有 Node/npm 的机器可使用 npx。npx 包只负责启动同一个下载/校验入口，不在 npm install/postinstall 时修改系统。保留既有卸载与分发修改；新增前端工具暂不纳入 Java 卸载范围。

验证记录：450 项完整回归通过；后续 npm prefix 隔离与 Git 前提检查用 29 项定向测试复验通过。临时 npm 包由 npm pack 生成，约 5.5 KB，仅 4 个文件；实际 npx 包经 HTTP 下载完整工具并在临时 HOME 安装 Node 18、验证新 zsh 和 npm 通过。所有前端官方资源已准备，原用户环境未修改；未公开发布 npm，未实现 Go TUI。
