# 下载服务的启动、停止与重启

维护者可以在 **Windows 或 macOS** 上准备资源、打包和运行下载服务。服务端只需 **Python 3.8+ 标准库**，不依赖 Bash、Homebrew、`hdiutil` 或系统压缩命令。下载到成员电脑的安装工具仍面向 **macOS**，Windows 服务端只托管这些文件。

以下命令都在项目根目录执行。Windows 优先用 `py -3`；没有 `py` 时，用 `python --version` 确认版本后改用 `python`。macOS 使用 `python3`。本轮已在 macOS 做自动化验证，包括 Windows 路径规则、CRLF 和归档权限；**尚未在 Windows 实机运行验收**。

## 部署前安装 Python 3

**在实际执行 `server/manage.py` 的维护者电脑或服务器上安装 Python**；如果资源准备、打包和托管分别在不同机器上进行，这些机器都需要安装。成员 Mac 运行下载后的安装、卸载客户端，无需安装 Python；卸载程序自带运行时。

最低要求为 **Python 3.8+**；新安装时选择官网仍在维护、且兼容服务器系统的 Python 3 正式版。服务端仅使用标准库，**无需安装第三方 Python 包，也无需执行 `pip install` 或创建虚拟环境**。已有 Python 时，先按对应系统运行下方验证命令；满足要求即可继续准备资源。

### Windows / Windows Server

1. 打开 [Python 官方 Windows 下载页](https://www.python.org/downloads/windows/)，选择与系统兼容的正式版。以下步骤使用 Python 3.13 / 3.14 提供的传统 **Windows installer `.exe`**；常见 x64 服务器选择 **Windows installer (64-bit)**，其他架构按实际系统选择。
2. 运行安装器，勾选 **Add python.exe to PATH**，保留 **Python Launcher（`py`）**、解释器和标准库。当前账号运行服务时可选 **Install Now**；若其他服务账号也需要使用，可通过 **Customize installation** 选择为所有用户安装，按提示使用管理员权限。
3. 安装完成后，关闭旧命令窗口，重新打开 PowerShell，进入项目根目录执行：

```powershell
py -3 --version
py -3 -c "import sys; assert sys.version_info >= (3, 8), '需要 Python 3.8 或更新版本'; print(sys.executable)"
py -3 server/manage.py --help
py -3 server/manage.py prepare --dry-run
```

没有 `py` 但已将 Python 加入 `PATH` 时，将上述 `py -3` 全部替换为 `python`。后台任务应使用验证命令打印出的解释器绝对路径，且在实际运行服务的账号下再次验证。

传统安装器的选项说明见 [Python 官方 Windows 安装文档](https://docs.python.org/3.14/using/windows.html#the-full-installer-deprecated)。

### macOS

1. 打开 [Python 官方 macOS 下载页](https://www.python.org/downloads/macos/)，选择兼容当前 macOS 的正式版 **macOS 64-bit universal2 installer `.pkg`**，同时支持 Apple Silicon 和 Intel；无需先安装 Homebrew。
2. 双击 `.pkg` 并按安装向导完成安装。随后在 `/Applications/Python 3.x/` 中双击 **Install Certificates.command**（`3.x` 替换为实际安装版本），完成 Python 的 HTTPS 证书初始化；该步骤需要联网，资源下载会使用这些证书。
3. 重新打开终端，进入项目根目录执行：

```bash
python3 --version
python3 -c "import sys; assert sys.version_info >= (3, 8), '需要 Python 3.8 或更新版本'; print(sys.executable)"
python3 server/manage.py --help
python3 server/manage.py prepare --dry-run
```

安装与证书初始化说明见 [Python 官方 macOS 安装文档](https://docs.python.org/3/using/mac.html#installation-steps)。

### 验证结果与常见问题

版本命令应输出 `Python 3.x.y`，版本至少为 3.8；版本检查命令应正常退出并打印解释器路径；`--help` 应显示 `start`、`prepare`、`package`、`preview`、`serve`；`prepare --dry-run` 应显示资源准备计划。以上验证不会下载资源、打包或启动服务，通过后再执行下一节的正式命令。

| 现象 | 处理方式 |
| --- | --- |
| 提示找不到 `py`、`python` 或 `python3` | 先重新打开命令窗口；Windows 检查安装器的 Launcher / PATH 选项，macOS 用 `command -v python3` 检查命令位置 |
| 版本低于 3.8，或仍指向旧 Python | 检查打印出的解释器路径，使用新安装的解释器绝对路径执行脚本 |
| Windows 输入 `python` 打开 Microsoft Store | 优先使用 `py -3`；若使用 `python`，检查应用执行别名与 PATH 是否指向已安装的解释器 |
| macOS 下载资源时报 `CERTIFICATE_VERIFY_FAILED` | 确认已完成对应版本的 `Install Certificates.command`；企业代理证书由团队 IT 配置 |

内网服务器无法访问官网时，可在可联网电脑下载对应的完整 `.exe` / `.pkg` 安装包，再传到服务器安装；Mac 的证书初始化还需可用网络或团队配置的证书环境。Python 安装包不包含在本项目的成员启动包或资源清单中。

## 发布前准备界面与卸载工具

先按[TUI 构建步骤](environment/tui.md#构建与分发)生成 `resources/tui/` 四个文件并带到服务器。它包含 arm64 / amd64 两个 Go 程序、清单和许可；成员无需 Go，服务器打包前会核对源码和产物摘要。

在 Mac 上按[成员卸载构建步骤](environment/cleanup.md#维护者构建成员卸载工具)生成 `resources/cleanup/cleanup-macos-universal2`、`manifest.json`、`THIRD_PARTY_NOTICES.txt`，将整个目录随项目带到实际服务器。该步骤需要单独的 Mac 构建环境；服务端仍只依赖 Python 标准库。

`package` / `start` 会核对可执行文件 SHA-256、卸载源码摘要与 arm64 / x86_64 架构，缺失或不一致时在替换发布文件前退出。修改 `tools/uninstall_java_gradle.py` 后必须重新构建。Windows 服务器仅使用 Mac 生成的成品，不能在 Windows 上重建 Mac 卸载程序。

## 一键启动：默认部署方式

在**实际运行下载服务的机器**上，进入项目根目录执行：

Windows PowerShell：

```powershell
py -3 server/manage.py start
```

macOS 终端：

```bash
python3 server/manage.py start
```

`start` 自动检测本机活动 IPv4 地址；只有一个候选时直接使用，有多个候选时在终端列出并要求选择序号。非交互环境有多个候选，或未检测到可用地址时，须显式传入 `--server`。它不采用客户端 Shell 配置中的默认 `127.0.0.1` 地址。

选定地址后，脚本先绑定 `0.0.0.0:8080`，再校验本地资源、补缺下载、带资源打包到 `dist/server`，最后开始提供 HTTP 下载并显示实际的 `start.zip` 链接。端口已占用时会在准备资源和改写发布文件前退出，不会关闭已有服务。

重复运行会复用校验通过的资源；校验失败的文件保留原样并报错，须检查后移走异常文件再重试。首次缺少资源时需要联网下载，默认资源库为 `resources/`。保持终端窗口运行，并从成员电脑验证显示的链接；自动选址不能保证防火墙、VPN 或网段之间允许访问。IP 变化后重新 `start`，并让成员重新下载、解压启动包。

可按需显式指定地址、端口或目录：

```bash
python3 server/manage.py start --server "192.168.1.20" --port 8082
python3 server/manage.py start --output dist/server --resources-dir /absolute/path/team-resources --catalog resources/catalog.tsv
```

`--server` 接受主机名或 IPv4 地址，也可带端口（如 `192.168.1.20:8082`），不含协议或路径，不接受监听地址 `0.0.0.0`；显式传入会覆盖自动选择。带端口且未传 `--port` 时使用地址中的端口；两个参数都传入时，端口不一致会报错。`start` 固定使用 HTTP，配置了 HTTPS 时会报错并引导高级流程；HTTPS 反向代理或分机器部署请用下方高级步骤。

## 系统原生入口

原生入口与 `manage.py` 使用同一套操作：

| 系统 | 启动入口 | 默认行为 |
| --- | --- | --- |
| Windows | `server\start-server.cmd` | 尝试 `py -3` 或 `python`，执行一键 `start` |
| macOS | `server/start-server.command` | 使用 `python3`，执行一键 `start` |

两个入口均可直接双击；不带参数时等同于 `start`，默认输出目录 `dist/server`、监听 `0.0.0.0:8080`。也可传入子命令和参数，例如：

```powershell
.\server\start-server.cmd start --port 8082
.\server\start-server.cmd serve --bind 0.0.0.0 --port 8080
```

```bash
bash server/start-server.command start --port 8082
bash server/start-server.command serve --bind 0.0.0.0 --port 8080
```

macOS 的 `.command` 是便捷入口；服务端处理仍全部由 Python 完成。Windows 不需要运行这些 Bash 入口。

## 高级：分步准备或分机器部署

需要分开准备资源、打包和托管，或使用现有静态服务器时，可保留四步流程。将示例地址替换为成员可访问的真实下载地址；Windows 把 `python3` 换成 `py -3`：

```bash
python3 server/manage.py prepare
python3 server/manage.py prepare --verify
python3 server/manage.py package --server "192.168.1.20:8080" --scheme http --with-resources --output dist/server
python3 server/manage.py serve --directory dist/server --bind 0.0.0.0 --port 8080
```

`prepare` 复用已校验的文件；`package` 生成发布文件，不下载缺失资源或启动服务；`serve` 只读托管已经打包的目录，不改写包或安装软件。已完成打包且地址未变时，可只运行 `serve`。分机器部署时，把完整输出目录复制到实际服务器，再用 `serve --directory` 指向它；包内地址须是成员最终访问的地址。

`serve --bind 0.0.0.0` 允许其他电脑连接；默认不指定时只监听 `127.0.0.1`。`0.0.0.0` 是监听地址，不能作为成员下载地址。内置服务提供 HTTP；需要 HTTPS 时，由团队已有的 HTTPS 静态服务或反向代理提供，再用最终地址及 `package --scheme https` 打包，该参数本身不配置 TLS。

## 本机预览

预览会先绑定端口，再校验资源、重新打包并启动服务。端口已占用时直接退出，**不会关闭已有服务，也不会改写发布文件**。

```powershell
py -3 server/manage.py preview --port 8081
```

```bash
python3 server/manage.py preview --port 8081
# 既有 Mac 入口仍可使用，默认端口同样为 8081
bash tools/preview.sh --port 8081
```

看到“本机预览已就绪”后，保持窗口运行，下载 [本机启动包](http://127.0.0.1:8081/start.zip)，重新解压后运行。预览只监听 `127.0.0.1`，不能供其他电脑访问。

`preview` 默认端口是 **8081**，而 `start` / `serve` 默认是 **8080**。预览会把启动包的下载地址改成本机预览端口，退出时不会恢复旧的内网地址。因此正式分发前要重新运行 `start`，或在高级流程中用真实 `--server` 打包。运行成员的「开始配置.command」或「卸载环境.command」不会替维护者启动服务器。新 `start.zip` 同时包含两个入口；老用户需重新下载一次启动 ZIP，后续每次启动都会拉取服务器最新发布工具。

## 配置与优先级

可复制 [config.example.json](../server/config.example.json) 为 `server/config.json`，修改端口和目录；也可通过 `--config 文件路径` 指定另一份 JSON。示例仅保留 `output`、`resources_dir`、`directory`、`port` 等通用默认值，不预填下载地址、监听地址或协议。配置中的相对目录以项目根目录为基准，命令行中的相对目录以当前工作目录为基准。Windows JSON 路径可使用 `/`，或用 `\\` 表示反斜杠。

- **一键启动的地址：** 命令行 `--server` → 环境变量 `SERVER_ADDR` → JSON 的 `server` → 自动检测本机活动 IPv4 地址。不采用客户端 Shell 默认地址；环境变量或旧 JSON 中的 `127.0.0.1` / `localhost` 会被忽略并重新检测，显式命令行地址可用于本机测试。唯一候选可自动选用；非交互运行遇到多个候选、无候选或检测失败时须传 `--server`。固定监听 `0.0.0.0` 并使用 HTTP。
- **高级 `package` 的地址与协议：** 命令行 `--server` / `--scheme` → 环境变量 `SERVER_ADDR` / `SERVER_SCHEME` → JSON 的 `server` / `scheme` → `dev-kit/.support/config/env.sh` 中可安全读取的字面默认值 → `127.0.0.1:8080` / `http`。服务端不会执行该 Bash 配置文件；正式分发应显式指定最终下载地址。
- **其他服务端参数：** 命令行 → JSON → 内置默认值。`output` 控制打包目录，`resources_dir` 控制本地资源库，`directory` 控制 `serve` 的服务根目录，`port` 控制监听端口。`start` 可另用 `--catalog` 指定资源清单。
- **本机预览：** 固定绑定 `127.0.0.1`，按预览端口生成 HTTP 下载地址，不采用配置中的内网地址。

所有子命令都支持 `--help`。只更新成员脚本时，`package` 省略 `--with-resources`，会保留输出目录已有资源；仍需保留本地资源库供校验和生成成员清单。

## 停止、重启、后台运行与端口

服务默认在前台运行，保留终端或命令窗口即可。停止时回到该窗口按 **`Ctrl+C`**；重启时再次执行原 `start` 命令或双击原生入口。高级分步部署则再次执行原 `serve` 命令。服务停止不会删除发布文件。电脑重启后需重新启动服务，本工具没有自动配置后台常驻或开机自启。

需要后台长期运行时，将带显式 `--server` 的 `start` 命令，或已完成打包后的 `serve` 命令，交给团队的服务管理方式，例如 Windows 任务计划程序或 macOS `launchd`，由相应管理器负责启停、日志和重启；也可把发布目录交给现有 IIS/Nginx。不要假定关闭当前窗口后前台服务仍会继续运行。

端口占用时先查看，不要直接关闭不明进程：

```powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen
```

```bash
lsof -nP -iTCP:8080 -sTCP:LISTEN
```

若已是本工具服务，可继续使用现有地址；其他应用占用时换端口。一键启动改为 `start --port 8082`，预览改为 `preview --port 8082`；若显式 `--server` 含端口，也须同步修改。高级流程改端口时，同时更新打包时的 `--server` 和启动时的 `--port`。内网地址或端口变更后，让成员重新下载启动包。

## 服务根目录与下载验证

**网站根目录必须直接包含 `start.zip`，通常为 `dist/server`，不能使用仓库根目录。** `serve` 会检查发布目录是否已完整打包，拒绝符号链接越界读取，并只提供下载，不接受上传。

```text
请求 /dev-env/team-dev-env.tar.gz
    → 网站根目录/dev-env/team-dev-env.tar.gz
    → 本项目默认 dist/server/dev-env/team-dev-env.tar.gz
```

可以把发布目录复制到另一台 Windows 或 Mac 服务器，再用 `serve --directory "实际发布目录"` 托管；须保留 `dev-env/`、`resources/` 及校验文件。维护脚本仍从项目中的 `server/manage.py` 运行；使用绝对目录参数后，托管位置不受启动位置影响。

从成员 Mac 检查以下地址，应返回 `200 OK`，再用浏览器下载和运行：

```bash
curl -fI "http://192.168.1.20:8080/start.zip"
curl -fI "http://192.168.1.20:8080/dev-env/team-dev-env.tar.gz"
curl -fI "http://192.168.1.20:8080/dev-env/team-dev-env.tar.gz.sha256"
```

| 现象 | 检查与处理 |
| --- | --- |
| 找不到 Python 或版本过低 | 先完成[部署前安装 Python 3](#部署前安装-python-3)并验证，再启动服务 |
| 连接被拒绝或超时 | 服务是否运行、内网/VPN是否可达、IP/端口和防火墙是否正确 |
| `HTTP 404` | 检查启动器显示的完整 URL、端口所属服务，以及网站根目录和发布文件 |
| 只有 `start.zip` 能下载 | 检查是否遗漏 `dev-env`、`resources` 或 `.sha256` 文件 |
| 本机可用、其他电脑不可用 | 检查所选 IP、成员网段、VPN 和防火墙；高级 `serve` 确认使用 `--bind 0.0.0.0` |
| 自动选址失败或后台启动要求地址 | 用 `start --server "实际主机或IP"` 显式指定；同时传 `--port` 时，端口须一致 |
| 改地址或端口后仍请求旧地址 | 重新 `start`（高级流程重新打包），并下载、解压新的 `start.zip` |

完整发布文件清单见[内网分发指南](distribution.md)，资源准备方式见[资源指南](resources/README.md)。
