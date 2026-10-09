# 前端环境安装与 npx 入口

nvm、iTerm2、Oh My Zsh 与 JDK、Gradle、IDEA 共用 `devtool-helper.sh install`。在安装页勾选组件、左右键调整 Node 范围、Enter 直接预检并安装；无独立 frontend 页面或数字菜单。一键安装全部包含六类工具，顺序固定为 JDK → Gradle → nvm/Node → iTerm2 → Oh My Zsh → IDEA/插件。

## 版本、默认与配置

| 项目 | 固定版本及范围 |
| --- | --- |
| nvm | 0.40.8，默认 `~/.nvm`，已有可用管理器复用 |
| Node | 默认安装 14.21.3；可选 10.24.1、18.20.8、22.23.3 或 all，各自配套 npm，安装到 `NVM_DIR/versions/node/` |
| iTerm2 | 3.7.3，macOS 13+，当前 `$HOME/Applications/iTerm.app` |
| Oh My Zsh | 固定提交，默认 `~/.oh-my-zsh`；git、z、zsh-autosuggestions、zsh-syntax-highlighting |

Node 可选 `none|10|14|18|22|all`：安装页、一键全部及省略 --node-version 时默认选择并安装 Node 14.21.3。`none` 仅安装/配置 nvm，不下载 Node、不改 default；显式 `all` 才安装四版，首次或旧 default 失效时回退到14，保留已有有效 default（包括历史16）；单版把该版设为默认，默认单版14同样遵循此规则，变更在选择页展示。新安装不支持 16，已有版本不自动卸载；nvm 本身仍可使用其他既有版本。

Node 10/14 使用官方 x64 包，Apple Silicon 必须已有可用 Rosetta；预检失败会停止，不自动安装 Rosetta 或编译源码。18/22 按 Mac 架构下载；具体来源、大小及摘要见[资源来源](../resources/frontend-sources.md)。选择的二进制须真实运行和验证路径后才能报告完成。

程序自动写好 `NVM_DIR` 和加载区块，Zsh 使用 `${ZDOTDIR:-$HOME}/.zshrc`，Bash 使用 `~/.bash_profile`，显式 `SHELL_PROFILE` 优先；实际位置记录供清理。仅安装 nvm 时用 --no-use 验证，可没有 Node。修改前保存首次 `.team-frontend.bak`，相同配置不重复追加。支持 NVM_DIR、ZSH、ZSH_CUSTOM，保留 Java 环境、用户主题和已有插件。

Oh My Zsh 需要可用 Git；会识别系统 Git/CLT 占位程序并提示，不自动安装开发工具。新框架的固定快照禁用自动更新，外部框架保留其政策；语法高亮按需要最后加载，已有用户加载次序保留。工具不执行上游在线 install.sh、不运行 chsh、不安装主题/字体。iTerm2 验证标识、版本、可执行文件及签名，保存绑定应用的来源收据，不自动启动或设为默认终端。

## 安装后切换 Node

新开终端加载自动配置，或在原终端使用结果页显示的实际路径；下面仅为默认目录且对应版本已安装时的示例：

```bash
export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"
nvm ls
nvm use 10
nvm use 14
nvm use 18
nvm use 22
nvm alias default 14
nvm use default
node -v
npm -v
```

`nvm use` 只改变当前终端及其后续子进程；`nvm alias default` 设置新终端默认，不立即改变当前终端；`nvm use default` 把默认应用到当前终端。Node 的切换只由 nvm 完成，没有另一个 PATH 选择器或全局 node/npm 软链接。切换无需重跑 helper，也不依赖临时下载目录。

结果和报告按实际成功/复用状态列出版本、有效默认与加载指引。nvm-only 显示“本次未安装 Node”，不虚构默认或可用版本。helper 是父终端的子进程，安装验证不表示父终端已切换。统一组件日志与计划在 `~/Library/Logs/team-java-env/components/<本次记录>/`；底层前端叶子脚本记录仍按实际输出位置查看。

## 公共 CLI 与卸载

```bash
bash devtool-helper.sh install --components nvm,iterm2,oh-my-zsh --node-version all --dry-run
bash devtool-helper.sh install --components nvm --node-version 22
bash devtool-helper.sh install --components nvm --node-version none
bash devtool-helper.sh install --components iterm2
bash devtool-helper.sh uninstall --components nvm,iterm2,oh-my-zsh --dry-run
bash devtool-helper.sh uninstall
```

成员资源来自维护者 TAR 内 `.support/config/resources.tsv`，固定摘要不可绕过。公共组件标识是 nvm / oh-my-zsh；底层 node/zsh 脚本名称不是公共路由。frontend、help frontend、--frontend、--plain 已移除。

六组件卸载页可选择这些前端对象及具体实例，核对永久删除计划并输入 DELETE。nvm 与 Node 各自认领；外部版本、用户别名和未知内容保留。受管 Node 全局包随对应版本删除，影响会列入清单。Oh My Zsh/插件依赖可信来源快照，用户主题、外置 ZSH_CUSTOM 和修改内容保留，加载区块按实际记录清理。iTerm2 要求可信绑定收据，不自动退出当前宿主，偏好/历史/会话保留。详见[卸载指南](cleanup.md)。

## npm 打包与 npx 使用

`team-dev-env-preview` 仍标记 private，未公开发布；已有 Node >=14.14 / npm 的成员可运行。没有 Node 的电脑用 Shell helper，当前终端处于 Node 10 时先切换符合要求的版本或使用 helper。

```bash
mkdir -p dist
(cd npm-cli && npm pack --pack-destination ../dist)
npx --offline --yes --package ./dist/team-dev-env-preview-0.1.0.tgz team-dev-env --help
npx --offline --yes --package ./dist/team-dev-env-preview-0.1.0.tgz team-dev-env install --components nvm,iterm2,oh-my-zsh --node-version all --server 192.168.1.20:8080 --dry-run
```

npx 的 --help 和 --dry-run 都是本地启动器操作，不下载工具；移除 --dry-run 后才获取 schema 2 release.json/TAR 并校验统一入口。业务只读计划用 Shell helper 的动作后 --dry-run。组件参数在交互终端预选到同一安装页，Enter 开始；无 TTY 实际安装须明确组件，卸载仍需明确范围与确认。

薄包只含 Node 启动器、共用 `tools/devtool-helper.sh.in` 模板与说明，不含 SDK/私有地址，不在 npm 安装阶段修改环境。可用 --server、SERVER_ADDR、SERVER_SCHEME、--scheme https。启动时隔离 npm 临时 prefix，用户持久 .npmrc 不自动改写；现有 prefix/globalconfig 冲突按 nvm 提示处理。保留真实退出状态与终止信号。

npm 包仅显式 npm pack 时产生，常规服务发布不生成它。正式定名和发布需另行取得授权、确认 registry、移除 private 并检查包清单，本次说明不代表已登录或 npm publish。详见[npm 包说明](../../npm-cli/README.md)。
