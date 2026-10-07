# 前端运行环境与终端工具的官方资源来源

核对日期：2026-10-07。目标平台为 macOS Intel（x64）与 Apple Silicon（arm64）。本次在原有 14 项资源之后新增 10 项，继续使用 `runtime`、`software`、`plugins` 三个分组；文件统一放在 `resources/frontend/`，完整下载地址和固定 SHA-256 见 [catalog.tsv](../../resources/catalog.tsv)。

本次已从官方地址下载全部 10 个新增资源，计算完整文件 SHA-256 并检查归档内容；均已复制到 `resources/frontend/` 对应清单路径，并写入同名 `.sha256` 校验记录。五个 Node 包和 iTerm2 实际摘要均与官方值一致。没有安装到用户目录，也未启动这些工具；这份来源核对记录不代表完成目标电脑安装或业务项目验收。

## 固定资源与路径

下列路径相对于 `resources/`。`any` 代表当前两种 macOS 架构共用；iTerm2 是含 arm64、x86_64 的 Universal 应用，不表示可在其他操作系统运行。

| 资源 ID | 分组 | 固定版本 | 架构 | 保存路径 |
| --- | --- | --- | --- | --- |
| `nvm` | `runtime` | `0.40.8`（上游 tag `v0.40.8`） | `any` | `frontend/nvm/nvm.tar.gz` |
| `node14-macos-x64` | `runtime` | `14.21.3` | `x64` | `frontend/node/node-v14.21.3-darwin-x64.tar.gz` |
| `node16-macos-arm64` | `runtime` | `16.20.2` | `arm64` | `frontend/node/node-v16.20.2-darwin-arm64.tar.gz` |
| `node16-macos-x64` | `runtime` | `16.20.2` | `x64` | `frontend/node/node-v16.20.2-darwin-x64.tar.gz` |
| `node18-macos-arm64` | `runtime` | `18.20.8` | `arm64` | `frontend/node/node-v18.20.8-darwin-arm64.tar.gz` |
| `node18-macos-x64` | `runtime` | `18.20.8` | `x64` | `frontend/node/node-v18.20.8-darwin-x64.tar.gz` |
| `iterm2` | `software` | `3.7.3` | `any` | `frontend/iterm2/iTerm2.zip` |
| `oh-my-zsh` | `plugins` | `60c9a7a839b790cd905d0fd4419435124fd1bdc0` | `any` | `frontend/zsh/oh-my-zsh.tar.gz` |
| `zsh-autosuggestions` | `plugins` | `0.7.1`（上游 tag `v0.7.1`） | `any` | `frontend/zsh/zsh-autosuggestions.tar.gz` |
| `zsh-syntax-highlighting` | `plugins` | `0.8.0` | `any` | `frontend/zsh/zsh-syntax-highlighting.tar.gz` |

## Node 14 / 16 / 18 与 nvm

nvm 固定为官方 [v0.40.8 发布](https://github.com/nvm-sh/nvm/releases/tag/v0.40.8)的[源码 tar.gz](https://github.com/nvm-sh/nvm/archive/refs/tags/v0.40.8.tar.gz)。下载后的归档根目录为 `nvm-0.40.8`，包含 `nvm.sh`。它是 Shell 版本管理器，无需为两种 CPU 分别下载。使用源码归档不需要运行在线 `install.sh`。

Node 18 的最终补丁版核对为 **18.20.8**，与官方 [latest-v18.x 目录](https://nodejs.org/dist/latest-v18.x/)一致，清单采用固定版本目录。Node tar.gz 保持上游原始内容，内含各版本配套 npm；版本信息来自[官方发行索引](https://nodejs.org/dist/index.json)。

| Node | 包含的 npm | macOS 资源 | 官方维护结束日期 |
| --- | --- | --- | --- |
| 14.21.3 | 6.14.18 | x64 | 2023-04-30 |
| 16.20.2 | 8.19.4 | arm64、x64 | 2023-09-11 |
| 18.20.8 | 10.8.2 | arm64、x64 | 2025-04-30 |

这三条 Node 主版本线均已 **EOL**，用于复现团队现有项目环境；新项目应按项目要求选择仍受维护的版本。维护结束日期来自 [Node.js 官方发布计划](https://github.com/nodejs/Release/blob/main/schedule.json)，状态可对照[官方版本页面](https://nodejs.org/en/about/previous-releases)。

**Node 14 没有官方 Darwin arm64 二进制包。** 本清单只提供官方 x64 包；Apple Silicon 使用该包需要系统已有可用 Rosetta。nvm 的[官方 Apple Silicon 说明](https://github.com/nvm-sh/nvm/blob/v0.40.8/README.md#macos-troubleshooting)说明 Darwin arm64 正式二进制从 Node 16 开始提供；[Node 14 官方归档](https://nodejs.org/dist/v14.21.3/)也只有 Darwin x64 包。本工具链不提供源码编译替代。Rosetta 的适用系统及安装方式以 [Apple 官方说明](https://support.apple.com/en-us/102527)为准。

维护者若使用 `--arch arm64` 筛选准备资源，该筛选不会包含 `node14-macos-x64`；需要给 Apple Silicon 分发 Node 14 时，必须再单独准备这个 ID，或使用完整清单。架构字段不能为绕过筛选而将 x64 包标为 `any`。

| Node 包 | SHA-256（官方值，已下载验证） | 实测字节数 |
| --- | --- | ---: |
| [14.21.3 Darwin x64](https://nodejs.org/dist/v14.21.3/node-v14.21.3-darwin-x64.tar.gz) | `a024f0dd5a4c1f951b79959c3e991b30a5919a734ab3e197ae0ef439e5a538b5` | 32241321 |
| [16.20.2 Darwin arm64](https://nodejs.org/dist/v16.20.2/node-v16.20.2-darwin-arm64.tar.gz) | `6a5c4108475871362d742b988566f3fe307f6a67ce14634eb3fbceb4f9eea88c` | 29989231 |
| [16.20.2 Darwin x64](https://nodejs.org/dist/v16.20.2/node-v16.20.2-darwin-x64.tar.gz) | `d7a46eaf2b57ffddeda16ece0d887feb2e31a91ad33f8774da553da0249dc4a6` | 31266877 |
| [18.20.8 Darwin arm64](https://nodejs.org/dist/v18.20.8/node-v18.20.8-darwin-arm64.tar.gz) | `bae4965d29d29bd32f96364eefbe3bca576a03e917ddbb70b9330d75f2cacd76` | 39866069 |
| [18.20.8 Darwin x64](https://nodejs.org/dist/v18.20.8/node-v18.20.8-darwin-x64.tar.gz) | `ed2554677188f4afc0d050ecd8bd56effb2572d6518f8da6d40321ede6698509` | 41055784 |

摘要分别来自固定版本的官方文件：[v14.21.3 SHASUMS256.txt](https://nodejs.org/dist/v14.21.3/SHASUMS256.txt)、[v16.20.2 SHASUMS256.txt](https://nodejs.org/dist/v16.20.2/SHASUMS256.txt)、[v18.20.8 SHASUMS256.txt](https://nodejs.org/dist/v18.20.8/SHASUMS256.txt)。本次下载摘要与这些值逐一匹配，实测大小与 HTTP HEAD 一致；未执行 PGP 签名验证。后续分发仍须重新计算包的 SHA-256。

五个 Node tar.gz 均只有三个符号链接：`bin/npm` → `../lib/node_modules/npm/bin/npm-cli.js`、`bin/npx` → `../lib/node_modules/npm/bin/npx-cli.js`、`bin/corepack` → `../lib/node_modules/corepack/dist/corepack.js`，没有硬链接。安装时需要保留这些指向归档内部的相对链接；不能仅因链接目标包含 `..` 就拒绝合法安装包。

## iTerm2

官方[稳定版下载页](https://iterm2.com/downloads.html)当前推荐 **3.7.3，macOS 13+**。清单固定到 [iTerm2-3_7_3.zip](https://iterm2.com/downloads/stable/iTerm2-3_7_3.zip)，保存为 `frontend/iterm2/iTerm2.zip`。

本次下载文件为 **57887250 字节**；SHA-256 为 `eb7a166061e58602e3d4bdf69d92f2c8cf6a63feed002f6adc07128a71c8dc39`，与下载页 3.7.3 的 PGP 签名消息中公开的摘要一致。这里只对照摘要，未验证该 PGP 签名。

归档内应用名为 `iTerm.app`，`Contents/Info.plist` 标记版本 `3.7.3`、最低系统 `13.0`；`Contents/MacOS/iTerm2` 的 Mach-O fat header 同时包含 x86_64 和 arm64。因此同一个 ZIP 可供两种 Mac 架构使用。低于 macOS 13 时应跳过此资源，不能因 Node 可用而推断这版 iTerm2 也可用。

## Oh My Zsh 与常用插件

Oh My Zsh 不采用正式稳定版本号，固定到核对时官方 master 的完整提交 [60c9a7a839b790cd905d0fd4419435124fd1bdc0](https://github.com/ohmyzsh/ohmyzsh/commit/60c9a7a839b790cd905d0fd4419435124fd1bdc0)（提交时间 2026-10-06 UTC），使用该提交的[源码归档](https://github.com/ohmyzsh/ohmyzsh/archive/60c9a7a839b790cd905d0fd4419435124fd1bdc0.tar.gz)，避免 `master.tar.gz` 随上游变化。

该归档包含 `git`、`npm`、`node`、`nvm`、`z`、`extract` 等内置插件，无需再为这些插件下载独立归档。可按实际需要启用；其中 `nvm` 插件与安装器直接加载 `nvm.sh` 的方式应择一统一管理，避免重复初始化。内置插件内容可查[固定提交的 plugins 目录](https://github.com/ohmyzsh/ohmyzsh/tree/60c9a7a839b790cd905d0fd4419435124fd1bdc0/plugins)。

另收录两个外部插件：

- [zsh-autosuggestions v0.7.1](https://github.com/zsh-users/zsh-autosuggestions/tree/v0.7.1)，按历史输入显示建议；tag 对应提交 `e52ee8ca55bcc56a17c828767a3f98f22a68d4eb`。
- [zsh-syntax-highlighting 0.8.0](https://github.com/zsh-users/zsh-syntax-highlighting/tree/0.8.0)，为输入命令着色；tag 对应提交 `db085e4661f6aafd24e5acb5b2e17e4dd5dddf3e`。其[安装说明](https://github.com/zsh-users/zsh-syntax-highlighting/blob/0.8.0/INSTALL.md)要求最后加载。

归档保留各上游许可证。资源准备只下载文件；应由安装流程在独立目录解压、维护配置，并保留成员原有 `.zshrc`。固定源码归档不含 Git 元数据，不能直接依赖 Git pull 自动更新；升级应由维护者重新核对固定版本和校验值。

## GitHub 源码归档的摘要来源

nvm、Oh My Zsh 和两个外部插件未发现独立的官方 SHA-256 发布文件。下列值是 **2026-10-07 从上文官方固定 URL 实际下载后，在本地计算的摘要**，已写入清单用于固定这些字节；它们不是上游独立签名或独立发布的校验值。GitHub 入口重定向到官方 `codeload.github.com`，清单保留原固定 tag/commit 地址。

| 资源 | 实测 SHA-256 | 实测字节数 | 归档根目录 |
| --- | --- | ---: | --- |
| nvm | `7c5b2c4c78e6447b518860ead1f365056e9a03b3562903439bb401607b05a2ef` | 410527 | `nvm-0.40.8` |
| Oh My Zsh | `b76ccbc18fd732d9d897dd2edbf16519cb48d20f31e509f925d1bf41a8df859f` | 3499661 | `ohmyzsh-60c9a7a839b790cd905d0fd4419435124fd1bdc0` |
| zsh-autosuggestions | `0df7affff21cd87ed298e6a3970ed08a1dd66a6efa676454ee5b091ad503badf` | 29968 | `zsh-autosuggestions-0.7.1` |
| zsh-syntax-highlighting | `5981c19ebaab027e356fe1ee5284f7a021b89d4405cc53dc84b476c3aee9cc32` | 155914 | `zsh-syntax-highlighting-0.8.0` |

未来若 GitHub 重新生成归档导致字节变化，下载器应停止并报告校验不符，由维护者重新核对；不能自动刷新清单摘要以绕过验证。上述文件已准备到 `resources/`，发布前使用现有资源准备流程复验，再进行成员包构建和目标电脑验收。
