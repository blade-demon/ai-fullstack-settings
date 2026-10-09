# team-dev-env-preview

macOS 团队开发环境的 npm/npx 薄入口。运行它需要已有 Node >=14.14 和 npm；没有 Node 的电脑使用团队提供的 `devtool-helper.sh`，通过 `bash devtool-helper.sh` 启动。当前包名保持不变，`private: true`；仅供本地打包和验证。

```bash
team-dev-env install --server 192.168.1.20:8080
team-dev-env install --components all --server 192.168.1.20:8080
team-dev-env install --components nvm,iterm2,oh-my-zsh --node-version all --server 192.168.1.20:8080
team-dev-env install --components jdk,gradle --gradle-version 6.8 --server 192.168.1.20:8080
team-dev-env install --components nvm --node-version none --server 192.168.1.20:8080
team-dev-env uninstall --components nvm,iterm2,oh-my-zsh --server 192.168.1.20:8080
team-dev-env uninstall --server 192.168.1.20:8080 --dry-run
```

组件为 `jdk,gradle,nvm,idea,iterm2,oh-my-zsh` 或单独的 `all`。Gradle 支持 `4.5.1|6.8|all`；Node 新安装支持 `none|10|14|18|22|all`，安装页、一键全部及省略 --node-version 时默认选择并安装14.21.3。显式 all 才安装四版，首次或旧 default 失效时回退到14，有效 default 保留；单版（包括默认单14）设所选默认，`none` 只配置 nvm、不改默认。历史 Node 16 不会被自动卸载。`frontend`、`help frontend`、`--frontend` 和 `--plain` 已移除，联网前返回 `2`。

也可设置 `SERVER_ADDR`、`SERVER_SCHEME`，或使用 `--scheme https`。npm 的 `--help` 和 `--dry-run` 始终表示本地帮助和启动器预演，无需下载工具。需要最新业务帮助或只读安装/卸载计划时，使用 Shell helper 的 `install --help`、`install --dry-run` 或 `uninstall --dry-run`。

在交互终端中，安装参数会预选到同一安装页，按 Enter 预检并执行；无交互终端的实际安装必须明确 `--components`。卸载默认预览，保留删除清单与 `DELETE` 确认；入口不会自动增加 `--apply` 或 `--yes`。

维护者显式执行 `npm pack` 时，预打包步骤从唯一的 `tools/devtool-helper.sh.in` 复制模板到 `assets/devtool-helper.sh.in`，并清理固定旧模板。普通成员发布不会生成 npm 包。本包只包含入口、模板和说明，不包含团队服务器私有地址或 SDK。它下载 `release.json` 和固定 TAR，校验 schema 2、大小、摘要、归档安全和统一入口后再运行。

启动器隔离 npm 上下文中的临时 prefix 变量，保留终端与子进程退出状态，传递终止信号并等待清理。它不会修改用户持久 `.npmrc` 或父终端环境。当前终端使用 Node 10 时，先用 `nvm use` 切换至满足启动器要求的版本，或直接使用 Shell helper。
