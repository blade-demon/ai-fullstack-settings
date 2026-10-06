# 下载服务的启动、停止与重启

维护者可以在 **Windows 或 macOS** 上准备资源、打包和运行下载服务。服务端只需 **Python 3.8+ 标准库**，不依赖 Bash、Homebrew、`hdiutil` 或系统压缩命令。下载到成员电脑的安装工具仍面向 **macOS**，Windows 服务端只托管这些文件。

以下命令都在项目根目录执行。Windows 优先用 `py -3`；没有 `py` 时，用 `python --version` 确认版本后改用 `python`。macOS 使用 `python3`。本轮已在 macOS 做自动化验证，包括 Windows 路径规则、CRLF 和归档权限；**尚未在 Windows 实机运行验收**。

## 首次准备：资源 → 打包 → 启动服务

以服务器地址 `192.168.1.20:8080` 为例，请替换为成员可访问的真实地址。

Windows PowerShell：

```powershell
py -3 --version
py -3 server/manage.py prepare
py -3 server/manage.py prepare --verify
py -3 server/manage.py package --server "192.168.1.20:8080" --scheme http --with-resources --output dist/server
py -3 server/manage.py serve --directory dist/server --bind 0.0.0.0 --port 8080
```

macOS 终端：

```bash
python3 --version
python3 server/manage.py prepare
python3 server/manage.py prepare --verify
python3 server/manage.py package --server "192.168.1.20:8080" --scheme http --with-resources --output dist/server
python3 server/manage.py serve --directory dist/server --bind 0.0.0.0 --port 8080
```

`prepare` 复用已校验的文件；`package` 生成发布文件，不启动服务；`serve` 只读托管已经打包的目录，不重新打包或安装软件。资源完整后，日常只需再次运行 `serve`。打包不会自动下载缺失的资源。

`--bind 0.0.0.0` 显式允许其他电脑连接，服务器防火墙应按团队规则允许该端口。它是监听地址，不能作为成员下载地址。发送给成员的链接为 `http://192.168.1.20:8080/start.zip`；`--server` 中的地址、协议和端口必须与实际提供下载的服务一致。

内置服务提供 HTTP。`package --scheme https` 只改变成员下载 URL，不会为内置服务配置 TLS；需要 HTTPS 时，由团队已有的 HTTPS 静态服务或反向代理提供。

## 系统原生入口

原生入口与 `manage.py` 使用同一套操作：

| 系统 | 启动入口 | 默认行为 |
| --- | --- | --- |
| Windows | `server\start-server.cmd` | 尝试 `py -3` 或 `python`，托管已打包目录 |
| macOS | `server/start-server.command` | 使用 `python3`，托管已打包目录 |

两个入口不带参数时等同于 `serve`，默认目录 `dist/server`、监听 `127.0.0.1:8080`。必须先准备资源并打包；直接双击入口不会自动补齐发布文件。也可传入子命令，例如：

```powershell
.\server\start-server.cmd prepare
.\server\start-server.cmd package --server "192.168.1.20:8080" --with-resources
.\server\start-server.cmd serve --bind 0.0.0.0 --port 8080
```

```bash
bash server/start-server.command prepare
bash server/start-server.command package --server "192.168.1.20:8080" --with-resources
bash server/start-server.command serve --bind 0.0.0.0 --port 8080
```

macOS 的 `.command` 是便捷入口；服务端处理仍全部由 Python 完成。Windows 不需要运行这些 Bash 入口。

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

`preview` 默认端口是 **8081**，而 `serve` 默认是 **8080**。预览会把启动包的下载地址改成本机预览端口，退出时不会恢复旧的内网地址。因此正式分发前要重新用真实 `--server` 打包。运行成员的「开始配置.command」不会替维护者启动服务器。

## 配置与优先级

可复制 [config.example.json](../server/config.example.json) 为 `server/config.json`，修改地址、端口和目录；也可通过 `--config 文件路径` 指定另一份 JSON。配置中的相对目录以项目根目录为基准，命令行中的相对目录以当前工作目录为基准。Windows JSON 路径可使用 `/`，或用 `\\` 表示反斜杠。

- **打包地址与协议：** 命令行 `--server` / `--scheme` → 环境变量 `SERVER_ADDR` / `SERVER_SCHEME` → JSON 的 `server` / `scheme` → `dev-kit/.support/config/env.sh` 中可安全读取的字面默认值 → `127.0.0.1:8080` / `http`。服务端不会执行该 Bash 配置文件。
- **其他服务端参数：** 命令行 → JSON → 内置默认值。`output` 控制打包目录，`resources_dir` 控制本地资源库，`directory` 控制服务根目录，`bind` 与 `port` 控制监听。
- **本机预览：** 固定绑定 `127.0.0.1`，按预览端口生成 HTTP 下载地址，不采用配置中的内网地址。

所有子命令都支持 `--help`。只更新成员脚本时，`package` 省略 `--with-resources`，会保留输出目录已有资源；仍需保留本地资源库供校验和生成成员清单。

## 停止、重启、后台运行与端口

服务默认在前台运行，保留终端或命令窗口即可。停止时回到该窗口按 **`Ctrl+C`**；重启时再次执行原 `serve` 命令。服务停止不会删除发布文件。电脑重启后需重新启动服务，本工具没有自动配置后台常驻或开机自启。

需要后台长期运行时，将同一条 `serve` 命令交给团队的服务管理方式，例如 Windows 任务计划程序或 macOS `launchd`，由相应管理器负责启停、日志和重启；也可把发布目录交给现有 IIS/Nginx。不要假定关闭当前窗口后前台服务仍会继续运行。

端口占用时先查看，不要直接关闭不明进程：

```powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen
```

```bash
lsof -nP -iTCP:8080 -sTCP:LISTEN
```

若已是本工具服务，可继续使用现有地址；其他应用占用时换端口。预览可改为 `preview --port 8082`；内网服务改端口时，必须同时更新打包时的 `--server`、启动时的 `--port`，再让成员重新下载启动包。

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
| 找不到 Python 或版本过低 | 维护者安装团队认可的 Python 3.8+；Mac 成员运行安装客户端不需要 Python |
| 连接被拒绝或超时 | 服务是否运行、内网/VPN是否可达、IP/端口和防火墙是否正确 |
| `HTTP 404` | 检查启动器显示的完整 URL、端口所属服务，以及网站根目录和发布文件 |
| 只有 `start.zip` 能下载 | 检查是否遗漏 `dev-env`、`resources` 或 `.sha256` 文件 |
| 本机可用、其他电脑不可用 | 确认显式使用 `--bind 0.0.0.0`，且成员拿到的是服务器真实地址 |
| 改端口后仍请求旧地址 | 重新打包并下载、解压新的 `start.zip` |

完整发布文件清单见[内网分发指南](distribution.md)，资源准备方式见[资源指南](resources/README.md)。
