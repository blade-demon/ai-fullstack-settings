# 本地开发环境指南

目标平台为 macOS。成员下载 `devtool-helper.sh`，在终端运行 `bash devtool-helper.sh`；首页提供安装与配置、卸载工具及一键安装配置全部。无需预装 Python、Node、Go、Homebrew。方向键移动、空格选择组件、左右键选择版本，安装页 Enter 直接预检并执行；卸载另需核对实例、清单和 `DELETE`。

| 指南 | 内容 | 成员选择 |
| --- | --- | --- |
| [系统运行环境](runtime.md) | JDK 8、环境模块、Shell 加载 | `jdk` |
| [Gradle 安装与切换](gradle.md) | 4.5.1 / 6.8 / all，当前与持久默认 | `gradle`，自动补入 JDK 8 依赖 |
| [前端环境](frontend.md) | nvm、Node 10/14/18/22、iTerm2、Oh My Zsh | `nvm,iterm2,oh-my-zsh` |
| [IDE 与插件](ide.md) | IDEA 2025.3.6.1 和六个推荐插件 | `idea` |
| [安全卸载](cleanup.md) | 六组件与具体实例、来源及用户数据边界 | `uninstall` |
| [本地服务与数据](services.md) | 可选 MySQL、数据库客户端 | 维护者底层命令行 |
| [项目依赖](dependencies.md) | Lombok、Spring、MyBatis、数据库驱动 | 业务项目维护 |

全量默认按 JDK → Gradle → nvm/Node → iTerm2 → Oh My Zsh → IDEA/插件执行，Gradle 默认 4.5.1，安装页和一键全部默认选择并安装 Node 14.21.3；其他单版仍可选，显式 `all` 才安装四版，首次或旧 default 失效时回退到14，有效 default 保留。单版（包括默认单14）设置所选默认；只安装 nvm 可选 `none` 且不改默认；两版 Gradle 可并存。安装完成后使用 `gradle_use` / `nvm use` 切换，无需重跑 helper。helper 不能改变父终端，按结果指引加载或新开终端。

成员使用说明见[使用说明](../../dev-kit/使用说明.txt)，交互与进度见[TUI 指南](tui.md)，分发和服务器启停见[内网分发](../distribution.md)。旧双入口、frontend 路由、--plain 和数字菜单不再使用。新版 IDEA 不覆盖已有冲突应用；2024 不是新安装基线，先核对卸载范围。

服务端仍支持 Windows/macOS，运行文件的构建、锁、镜像和下载见[运行文件发布指南](runtime-release.md)。成员不执行项目构建；维护者保留底层 `repair-env.sh --project` 等检查和构建功能，它们与公共组件入口分别管理。记录见[修复历史](../repair-history.md)；历史结果不代表本次实机或业务项目已经验证。
