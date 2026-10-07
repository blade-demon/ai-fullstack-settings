# 前端环境安装与 npx 入口

Go TUI 的“安装前端环境”页面（普通模式菜单 `6`）提供独立前端环境安装；原菜单 `1` 继续只安装 JDK 8、Gradle 4.5.1、IDEA 和推荐 IDEA 插件。

| 前端子菜单 | 操作 |
| --- | --- |
| `1` | 安装 nvm、三版 Node、iTerm2、Oh My Zsh 和推荐插件 |
| `2` / `3` / `4` | 安装 nvm 及 Node 14 / 16 / 18 |
| `5` | 安装 nvm 及全部三版 Node |
| `6` | 安装 iTerm2 |
| `7` | 安装 Oh My Zsh 和推荐插件 |
| `0` | 返回主菜单；空输入不安装 |

## 版本、目录与现有配置

- nvm 固定为 0.40.8，默认安装在 `~/.nvm`；已有可用 nvm 会复用，未知或损坏目录不会覆盖。
- Node 固定为 14.21.3、16.20.2、18.20.8，安装到 nvm 的 `versions/node/`，包含各版本对应 npm。单独选择版本会设为 nvm default；全部安装时保留已有 default，首次默认 18.20.8。
- Node 14 只有官方 macOS x64 包；Apple Silicon 须已有可用 Rosetta。工具先检查，缺少时停止 Node 安装并说明原因，不自动安装 Rosetta或进行源码编译。Node 16 / 18 按 Mac 架构选择官方包。
- iTerm2 固定为 3.7.3，要求 macOS 13+，安装到 `/Users/用户名/Applications/iTerm.app`（当前 `$HOME/Applications`）。与 IDEA 共用个人应用目录规则，用户名由当前主目录确定，不额外拼接 `Users/用户名`。验证应用标识、版本、可执行文件和代码签名，不自动启动或设为默认终端。
- Oh My Zsh 使用固定提交，默认安装到 `~/.oh-my-zsh`；推荐插件为内置 `git`、`z`，以及 `zsh-autosuggestions`、`zsh-syntax-highlighting`。

Node 14 / 16 / 18 均已结束官方维护，保留它们用于团队旧项目兼容。版本来源、SHA-256、架构和 EOL 信息见[官方资源记录](../resources/frontend-sources.md)。

`.zshrc` 使用独立的 `team-frontend-env` 区块；修改前保留首次 `.team-frontend.bak`，重复运行相同配置不反复追加。支持 `ZDOTDIR`、`NVM_DIR`、`ZSH`、`ZSH_CUSTOM` 等显式环境变量。工具保留 Java 环境、用户主题和已有插件，不执行上游安装脚本、不运行 `chsh`、不安装字体或主题。Oh My Zsh 框架初始化需要可用 Git（即使不启用推荐插件）；安装器会识别缺少 Command Line Tools 时的系统 git 占位程序并提前提示，不执行该占位程序或自动安装开发工具。新开终端后配置生效。

本工具新安装的 Oh My Zsh 固定快照禁用自动更新，后续升级由维护者更新资源完成；复用外部框架时保留其更新政策。新框架或新加入的语法高亮最后加载；已经由用户加载的高亮保持原次序，避免重复加载或重写用户配置。

每次操作的组件日志和结果保存在 `~/Library/Logs/team-java-env/frontend/<本次记录>/`，包括 `steps.tsv`、`result.tsv` 和组件日志。任何组件失败都保留非零结果，不能将部分成功当作全部完成。新增工具使用独立来源记录，**当前 Java 环境卸载入口不删除 nvm、Node、iTerm2 或 Oh My Zsh**。

## 命令行

从仓库根目录运行；完整工具解压后将前缀 `dev-kit/` 去掉：

```bash
bash dev-kit/开始配置.command --frontend --dry-run
bash dev-kit/开始配置.command --frontend --component node --node-version 16
bash dev-kit/开始配置.command --frontend --component iterm2
bash dev-kit/开始配置.command --frontend --component zsh
```

客户端读取维护者生成的 `.support/config/resources.tsv`，仅从团队资源服务器下载，固定校验摘要。没有该清单时，应先完成服务端资源准备与打包；直接运行源码不是绕过清单校验的途径。

## npm 打包与 npx 使用

发布工具是 `npm publish`，运行工具是 `npx`。当前包临时命名为 `team-dev-env-preview`，标记 `private: true`，尚未公开发布。薄入口只包含 Node 启动器与共用 Bash 下载模板，不包含 SDK 安装包、用户配置或固定的私有服务器地址，也不在 npm 安装阶段修改系统。

在仓库根目录构建并验证本地包：

```bash
mkdir -p dist
(cd npm-cli && npm pack --pack-destination ../dist)
npx --offline --yes --package ./dist/team-dev-env-preview-0.1.0.tgz team-dev-env --help
npx --offline --yes --package ./dist/team-dev-env-preview-0.1.0.tgz team-dev-env frontend --server 192.168.1.20:8080 --dry-run
```

去掉最后一个命令的 `--dry-run` 才下载并运行前端安装流程；替换为实际团队服务器。也可使用 `SERVER_ADDR` / `SERVER_SCHEME`，或通过 `--scheme https` 指定 HTTPS。npx 入口的 `--dry-run` 仅显示目标地址与参数，不联网。启动子进程时隔离 npm 临时注入的 prefix 变量，避免影响 nvm；用户持久 `.npmrc` 不会被自动修改，既有 prefix/globalconfig 冲突仍需按 nvm 提示处理。

已有 Node 14.14+ / npm 的 Mac 可使用 npx；完全没有 Node 的机器仍需双击 `start.zip` 完成首次安装。命令 `team-dev-env install`、`frontend`、`uninstall` 共用下载、SHA-256 校验与安全解压；退出状态向上传递，卸载仍需确认。

正式发布前，在 `npm-cli/package.json` 中换成具有发布权限的正式包名、移除 `private`，确认公开或私有 registry，检查 `npm pack --dry-run` 清单，再执行 `npm publish`。此后可通过 `npx 正式包名 frontend --server 实际服务器` 运行。没有在本次工作中登录或发布到 npm。

Go + Bubble Tea 与该入口兼容：npm 包可继续作为启动层，由下载后的双击入口启动对应架构的 Go 程序。当前交互界面已使用 Go + Bubble Tea，界面与安装脚本分开；指定组件参数时仍可无界面执行。详见[TUI 指南](tui.md)。
