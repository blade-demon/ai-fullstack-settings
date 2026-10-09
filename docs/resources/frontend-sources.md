# 前端运行环境与终端工具的官方资源来源

原有前端资源核对日期：2026-10-07；当前 Node 集合与文件摘要复核：2026-10-09。目标为 macOS Intel x64 / Apple Silicon arm64。当前 catalog 共 25 项，其中 frontend 路径 11 项；资源下载来源和固定摘要以 [catalog.tsv](../../resources/catalog.tsv) 为准。

2026-10-09 重新读取六个现行 Node 原包，计算 SHA-256 与字节数，均匹配 catalog；新增 Node 10 x64 与 Node 22 双架构同时对照官方 SHASUMS256。资源已在源库，源库已有历史旁置记录保留；静态部署副本不另写 .sha256。本文没有执行用户安装或启动 SDK，不代表成员实机、业务构建或服务部署验收通过。

## 固定资源与路径

路径相对于 resources/，any 表示两种 Mac 架构共用，不表示支持其他系统。Node 16 不再列入新安装清单；旧文件与既有安装不因集合变化自动删除。

| 资源 ID | 分组 | 固定版本 | 架构 | 保存路径 |
| --- | --- | --- | --- | --- |
| `nvm` | `runtime` | `0.40.8` | `any` | `frontend/nvm/nvm.tar.gz` |
| `node14-macos-x64` | `runtime` | `14.21.3` | `x64` | `frontend/node/node-v14.21.3-darwin-x64.tar.gz` |
| `node18-macos-arm64` | `runtime` | `18.20.8` | `arm64` | `frontend/node/node-v18.20.8-darwin-arm64.tar.gz` |
| `node18-macos-x64` | `runtime` | `18.20.8` | `x64` | `frontend/node/node-v18.20.8-darwin-x64.tar.gz` |
| `iterm2` | `software` | `3.7.3` | `any` | `frontend/iterm2/iTerm2.zip` |
| `oh-my-zsh` | `plugins` | `60c9a7a839b790cd905d0fd4419435124fd1bdc0` | `any` | `frontend/zsh/oh-my-zsh.tar.gz` |
| `zsh-autosuggestions` | `plugins` | `0.7.1` | `any` | `frontend/zsh/zsh-autosuggestions.tar.gz` |
| `zsh-syntax-highlighting` | `plugins` | `0.8.0` | `any` | `frontend/zsh/zsh-syntax-highlighting.tar.gz` |
| `node10-macos-x64` | `runtime` | `10.24.1` | `x64` | `frontend/node/node-v10.24.1-darwin-x64.tar.gz` |
| `node22-macos-arm64` | `runtime` | `22.23.3` | `arm64` | `frontend/node/node-v22.23.3-darwin-arm64.tar.gz` |
| `node22-macos-x64` | `runtime` | `22.23.3` | `x64` | `frontend/node/node-v22.23.3-darwin-x64.tar.gz` |

## Node 10 / 14 / 18 / 22 与 nvm

nvm 固定为官方 [v0.40.8](https://github.com/nvm-sh/nvm/releases/tag/v0.40.8)的[源码归档](https://github.com/nvm-sh/nvm/archive/refs/tags/v0.40.8.tar.gz)，根目录 nvm-0.40.8 含 nvm.sh；不运行在线 install.sh。Node 使用固定版本目录，不在成员安装时查询 latest。当前原包的 npm/package.json 内容为：

| Node | 配套 npm | macOS 资源 |
| --- | --- | --- |
| 10.24.1 | 6.14.12 | x64 |
| 14.21.3 | 6.14.18 | x64 |
| 18.20.8 | 10.8.2 | arm64、x64 |
| 22.23.3 | 10.9.9 | arm64、x64 |

Node 10、14 无官方 Darwin arm64 包，Apple Silicon 要求已有可用 Rosetta；不回退源码编译或自动安装 Rosetta。依据为 [Node 10 固定归档](https://nodejs.org/download/release/v10.24.1/)、[Node 14 固定归档](https://nodejs.org/dist/v14.21.3/)和[nvm macOS 说明](https://github.com/nvm-sh/nvm/blob/v0.40.8/README.md#macos-troubleshooting)。18/22 按本机架构使用原包，具体系统兼容仍需目标电脑运行验证。

维护者 --arch arm64 筛选不会包含 node10-macos-x64 / node14-macos-x64；Apple Silicon 要使用两版时另外准备对应 ID 或使用完整清单，不把 x64 包标成 any。安装前 Rosetta 检查和实际版本运行验证都不能由仅下载通过代替。

| Node 包 | SHA-256 | 2026-10-09 本地实测字节数 |
| --- | --- | ---: |
| [node-v10.24.1-darwin-x64.tar.gz](https://nodejs.org/download/release/v10.24.1/node-v10.24.1-darwin-x64.tar.gz) | `8088968a896e17c21b98187f8083291df9c88d0baa100a6cb9553e53c4fb17f8` | 18839577 |
| [node-v14.21.3-darwin-x64.tar.gz](https://nodejs.org/dist/v14.21.3/node-v14.21.3-darwin-x64.tar.gz) | `a024f0dd5a4c1f951b79959c3e991b30a5919a734ab3e197ae0ef439e5a538b5` | 32241321 |
| [node-v18.20.8-darwin-arm64.tar.gz](https://nodejs.org/dist/v18.20.8/node-v18.20.8-darwin-arm64.tar.gz) | `bae4965d29d29bd32f96364eefbe3bca576a03e917ddbb70b9330d75f2cacd76` | 39866069 |
| [node-v18.20.8-darwin-x64.tar.gz](https://nodejs.org/dist/v18.20.8/node-v18.20.8-darwin-x64.tar.gz) | `ed2554677188f4afc0d050ecd8bd56effb2572d6518f8da6d40321ede6698509` | 41055784 |
| [node-v22.23.3-darwin-arm64.tar.gz](https://nodejs.org/download/release/v22.23.3/node-v22.23.3-darwin-arm64.tar.gz) | `23b25245dcfb9af7262f8ff142e9e2e0af025368117329e7a7458a51e5922f53` | 49963763 |
| [node-v22.23.3-darwin-x64.tar.gz](https://nodejs.org/download/release/v22.23.3/node-v22.23.3-darwin-x64.tar.gz) | `8a677b0219178efd6eb0e475457c4afb452b521a92f6e67845a73bd85727f2a8` | 51142049 |

新增摘要已对照官方 [v10.24.1 SHASUMS256.txt](https://nodejs.org/download/release/v10.24.1/SHASUMS256.txt)、[v22.23.3 SHASUMS256.txt](https://nodejs.org/download/release/v22.23.3/SHASUMS256.txt)。14/18 沿用 2026-10-07 的官方核对记录：[v14.21.3](https://nodejs.org/dist/v14.21.3/SHASUMS256.txt)、[v18.20.8](https://nodejs.org/dist/v18.20.8/SHASUMS256.txt)；本次重新计算文件摘要一致，没有重复研究版本，也未做 PGP 签名验证。后续分发仍计算完整 SHA-256。

2026-10-09 读取归档成员确认：Node 10 只有 bin/npm、bin/npx 两个内部相对链接；14/18/22 另有 bin/corepack，共三个；均无硬链接。链接目标分别位于 lib/node_modules/npm/bin 与 corepack/dist，不应仅因相对目标含 .. 拒绝合法内部链接。

公共 --node-version 支持 none/10/14/18/22/all，安装页、一键全部及省略该参数时默认选择并安装14.21.3。显式 all 才安装四版，首次或旧 default 失效时回退到14，已有有效 default 保留；none 不安装 Node、不改 default，单版（包括默认单14）设置所选默认。实际加载、nvm use 与 alias default 的区别见[前端指南](../environment/frontend.md)。

## iTerm2

2026-10-07 核对的官方[稳定版下载页](https://iterm2.com/downloads.html)提供 **3.7.3，macOS 13+**。清单固定到 [iTerm2-3_7_3.zip](https://iterm2.com/downloads/stable/iTerm2-3_7_3.zip)，保存为 `frontend/iterm2/iTerm2.zip`。

本次下载文件为 **57887250 字节**；SHA-256 为 `eb7a166061e58602e3d4bdf69d92f2c8cf6a63feed002f6adc07128a71c8dc39`，与下载页 3.7.3 的 PGP 签名消息中公开的摘要一致。这里只对照摘要，未验证该 PGP 签名。

归档内应用名为 `iTerm.app`，`Contents/Info.plist` 标记版本 `3.7.3`、最低系统 `13.0`；`Contents/MacOS/iTerm2` 的 Mach-O fat header 同时包含 x86_64 和 arm64。因此同一个 ZIP 可供两种 Mac 架构使用。低于 macOS 13 时不可选择安装此资源；全量预检会提示调整范围，不能因 Node 可用而推断这版 iTerm2 也可用。

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
