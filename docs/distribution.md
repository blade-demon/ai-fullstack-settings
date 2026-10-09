# 内网分发指南

Windows/macOS 维护者用 Python 3.8+ 标准库准备资源、打包和托管；成员客户端仅支持 macOS。成员只下载一个 `devtool-helper.sh`，在终端运行，无需填写服务器地址或预装 Python、Node、Go、Homebrew。服务器原生启动入口 `server/start-server.command` / `.cmd` 保持不变。

## 成员入口

```bash
bash devtool-helper.sh
bash devtool-helper.sh install
bash devtool-helper.sh uninstall
bash devtool-helper.sh help install
bash devtool-helper.sh --dry-run install --components all
bash devtool-helper.sh install --components jdk,gradle --gradle-version all --dry-run
bash devtool-helper.sh install --components nvm,iterm2,oh-my-zsh --node-version all
bash devtool-helper.sh uninstall --components nvm,iterm2,oh-my-zsh --dry-run
```

无参数且有 TTY 打开首页；`install` / `uninstall` 直接打开对应选择页。安装页方向键移动、空格勾选、左右键选择版本，Enter 直接预检并安装，没有额外计划确认页；空选择不执行，预检失败留在选择页。卸载默认全不选，选择组件及实例，核对具体删除与配置计划后输入 `DELETE`。安装、取消、版本切换及卸载边界见[环境总入口](environment/README.md)。

组件标识为 `jdk,gradle,nvm,idea,iterm2,oh-my-zsh` 或单独的 `all`。Gradle 版本支持 `4.5.1|6.8|all`，Node 支持 `none|10|14|18|22|all`。全量包含六组件，按 JDK → Gradle → nvm/Node → iTerm2 → Oh My Zsh → IDEA/插件执行；Gradle 默认 4.5.1，Node 支持固定 10.24.1 / 14.21.3 / 18.20.8 / 22.23.3；安装页、一键全部及省略 --node-version 时默认选择并安装 14.21.3。显式 all 才安装四版，首次或旧 default 失效时回退到 14，有效 default 保留。单版（包括默认单14）设置所选默认，nvm-only 不改 default。已有 Node 16 保留。

`help`、`help install` / `help uninstall` 和动作前全局 `--dry-run` 在本地完成，不联网或创建下载目录。动作后的 `--help` / `--dry-run` 下载工具后显示业务帮助或只读计划。无 TTY 实际安装必须明确组件；非交互真删必须明确组件并同时指定 `--apply --yes`，外壳不自动加入这些执行参数。

`frontend`、`help frontend`、`--frontend`、`--plain` 与旧数字菜单已移除，非法入口在联网前返回 `2`。TUI 缺失或损坏应重新下载，不回退文本菜单。成员 `.sh` 以终端运行为准，不承诺双击，不通过后缀或删除隔离标记免除 macOS 安全检查。

## 三个成员发布文件

常规 `start` / `package` 只生成：

```text
dist/server/
├── devtool-helper.sh
├── release.json
└── dev-env/
    └── team-dev-env.tar.gz
```

`release.json` 使用 **schema 2**，顶层为 `schema,interface,version,created_at,server,runtime_sources,launcher,bundle`。`interface` 为 `go-tui`；`runtime_sources` 记录 TUI 与 cleanup 源码摘要；`launcher`、`bundle` 各只有 `path,size,sha256`，路径分别固定为 `devtool-helper.sh`、`dev-env/team-dev-env.tar.gz`。不再使用旧 `artifacts` 集合或旁置 TAR 摘要。

成员版本为 `go-tui-<TAR SHA-256 前 12 位>`。helper 每次获取最新 `release.json` 和 TAR，检查 schema、字段类型、固定路径、大小、摘要、版本及归档安全后才执行统一内部入口；下载期间版本变化导致不匹配时停止，请重新运行。工具退出或取消后清理临时下载目录，不以旧缓存掩盖失败。`serve` 同时核对 helper 与 TAR 的实际大小/摘要，拒绝旧 schema、损坏或退场文件残留的目录。

固定退场文件仅为 `start.zip`、`start.command`、`uninstall.command`、`team-dev-env.zip`、`dev-env/team-dev-env.tar.gz.sha256`。打包先准备并验证新版，成功后清理这些固定普通旧文件；未知文件、源资源记录不随迁移删除，异常链接或清理失败会报错。旧成员须重新下载 helper；只更新服务器 TAR 无法替换成员手里的旧入口模板。

TAR 内部结构：

```text
team-dev-env/
└── .support/
    ├── install_env.sh                # 维护者底层修复能力
    ├── cleanup/                      # universal2 卸载工具、manifest、许可
    ├── tui/                          # 两架构 Go 程序、manifest、许可
    ├── config/
    │   ├── env.sh
    │   ├── team.sh                   # 固定团队下载地址
    │   └── resources.tsv             # 本次软件资源路径与确定摘要
    └── scripts/
        └── run-tool.sh               # install|uninstall 唯一内部适配入口
```

TAR 不含两份旧 `.command`、`menu.sh`、使用说明或 ZIP 副本。成员不需保留、移动或编辑内部工具目录；维护者解压调试可运行 `bash team-dev-env/.support/scripts/run-tool.sh install --help`。SDK 原包与软件、插件资源独立托管，不塞入 TAR。清单、运行文件校验和第三方许可继续保留。

## 一键准备与启动

先完成[Python 安装与验证](service-startup.md#部署前安装-python-3)，在实际下载服务器的仓库根目录运行；Windows 改用 `py -3`：

```bash
python3 server/manage.py start
```

自动选 IPv4，多候选时选择；先绑定 `0.0.0.0:8080`，再准备运行文件和安装资源、生成三个发布文件、校验并启动服务。缺失或过期运行文件按 schema 1 的 `resources/runtime-lock.json` 下载匹配的运行文件 ZIP；下载服务器不编译、不执行 Mac 二进制。源码变更后的运行文件 Release 由维护者显式构建和上传，见[运行文件发布指南](environment/runtime-release.md)。

默认安装资源库为 `resources/`，现清单 25 项；已有有效文件复用，损坏安装资源保留报错。默认服务将本次 TAR 清单中的 `/resources/...` URL **只读映射到源资源库**，不重复复制大包。`start` / `serve` 只提供三个固定文件和当前包资源清单中的路径，GET/HEAD 对退场或未知文件返回 `404`，目录浏览关闭，后来复制文件或查询参数不扩大访问范围。

| 参数 | 含义 |
| --- | --- |
| `--server HOST[:PORT]` | 成员可访问的主机，覆盖自动选址，不含协议或路径 |
| `--port PORT` | 默认 8080；与显式地址中的端口须一致 |
| `--output DIR` | 发布目录，默认 `dist/server` |
| `--resources-dir DIR` | 本地资源库，默认 `resources` |
| `--catalog FILE` | 指定资源清单 |
| `--with-resources` | 显式复制软件资源供外部静态服务器部署 |
| `--runtime-base-url URL` | 匹配运行文件 ZIP 所在镜像目录，不绕过锁 |

`git pull` 不打包或重启。停止自己管理的旧服务再运行 `start`，核对就绪输出及 HTTP `/release.json`。端口占用时本次没有准备或改写发布物，原地址可能仍为旧版。地址固化到 helper 与内部团队配置；IP/端口变化后重新打包，并让成员重新下载 helper。完整配置优先级、启停、端口与 Python 排错见[服务启动指南](service-startup.md)。

## 分步与外部静态服务器部署

```bash
python3 server/manage.py prepare-runtimes
python3 server/manage.py prepare
python3 server/manage.py prepare --verify
# 本机 Python 服务：不复制软件资源
python3 server/manage.py package --server "192.168.1.20:8080" --scheme http --output dist/server
python3 server/manage.py serve --directory dist/server --resources-dir resources --bind 0.0.0.0 --port 8080
```

`package` 只校验本地运行文件及软件资源并打包，不联网、不启动服务。`serve` 验证已有目录后只读托管，显示该目录自身版本，不保证与最新源码一致。自定义源资源库时，给 `serve --resources-dir` 传同一个位置；有部署副本时可使用该副本，显式源库参数优先。

需要把发布目录复制到另一台静态服务器时，显式部署资源副本：

```bash
python3 server/manage.py package --server "team-download.example:8080" --scheme http --with-resources --output dist/server
```

上传三个文件及 `resources/` 内本次清单所需原包，保留相对路径。资源部署副本不另写 `.sha256`；摘要在 TAR 内资源清单，源资源库中的首次下载记录保留。省略 `--with-resources` 时不生成副本，已有副本可保留。网站根目录必须是实际发布目录，不能是仓库根目录。外部服务要限制为三个固定文件与当前资源清单，禁止目录浏览及未知/退场路径；不要因为磁盘存在额外文件就公开托管它。

HTTPS 由现有静态服务或反向代理提供证书，打包使用最终地址及 `--scheme https`；该参数不配置 TLS，`start` 固定 HTTP。发布时协调替换 helper、TAR、release.json，避免跨版本混用。

## 本机预览与下载验证

```bash
python3 server/manage.py preview --port 8081
# 需要保留预览文件时才显式指定输出目录
python3 server/manage.py preview --port 8081 --output /absolute/path/preview
```

默认预览只监听 `127.0.0.1:8081`，先占端口、补齐运行文件、校验已有软件资源并打包到临时目录；退出清理，忽略正式 output 配置，不改 `dist/server`。显式 `--output` 的预览目录保留。预览不下载缺少的软件资源，先运行 `prepare`；成员 helper 不启动服务器。

分发前从成员机器核对：

```bash
curl -fI "http://192.168.1.20:8080/devtool-helper.sh"
curl -fI "http://192.168.1.20:8080/dev-env/team-dev-env.tar.gz"
curl -fsS "http://192.168.1.20:8080/release.json"
```

核对实际版本和来源地址、下载 helper 并运行帮助/预演、验证六组件选择和实际结果、分别验证 Mac 架构与系统要求。再进行团队批准的实机安装、卸载和业务项目构建验收；本指南不声称这些验收已完成。发送就绪输出中的 `http://实际地址/devtool-helper.sh?v=go-tui-…` 链接。

| 现象 | 处理 |
| --- | --- |
| 连接拒绝/超时 | 检查服务、内网/VPN、防火墙、IP/端口 |
| HTTP 404 | 核对端口所属服务、根目录、三个发布文件及清单资源映射 |
| TAR 大小或摘要不符 | 停止本次运行，维护者核对同一次发布；可能发布期间更新，重跑获取完整新版 |
| 界面仍旧 | 核对本次 start 是否完成及 release.json 实际版本，重新下载 helper |
| serve 拒绝目录 | 重新 start/package；不手改摘要或留下固定退场文件 |
| 软件下载缺失 | 本地服务核对源资源库；外部静态服务核对显式部署副本 |
| 当前终端仍用旧版本 | 按结果加载持久配置或新开终端；IDEA 另行确认 SDK/分发 |
| 部分组件失败 | 查看组件日志、真实退出码和保留项，不把下载完成当作整体完成 |

## 维护者底层能力与 npx

公共组件入口只负责安装/卸载组件。业务项目、仅下载、历史及 MySQL 仍由维护者底层脚本管理：

```bash
bash dev-kit/.support/scripts/repair-env.sh --scope all --project "/absolute/path/to/java-project" --dry-run
bash dev-kit/.support/scripts/repair-env.sh --scope all --project "/absolute/path/to/java-project"
bash dev-kit/.support/scripts/repair-env.sh --scope gradle --gradle-version 6.8
bash dev-kit/.support/scripts/check-env.sh --project "/absolute/path/to/java-project"
bash dev-kit/.support/scripts/history.sh
bash dev-kit/.support/scripts/download-tools.sh --id lombok
bash dev-kit/.support/scripts/services/mysql.sh up --dry-run
```

底层 `--scope all` 是 Java 修复范围，公共 `--components all` 才是六组件。省略项目不构建，指定项目后的终端构建仍不代替 IDEA GUI 同步。业务依赖、JDBC 驱动和 MySQL 镜像另行准备。npm/npx 适合已有 Node/npm 的成员，薄入口只有 install/uninstall，保持 private 且按需 npm pack；详见[前端指南](environment/frontend.md#npm-打包与-npx-使用)。
