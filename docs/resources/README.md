# 资源准备与使用

维护者用 Windows/macOS 的 Python 3.8+ 标准库把官方原包准备到源资源库 `resources/`；成员安装客户端仅支持 macOS。成员入口为 `devtool-helper.sh`，常规分发只有 helper、TAR、release.json，软件资源独立托管。

## 清单范围

以 [catalog.tsv](../../resources/catalog.tsv) 为依据，当前共 **25 项**：

| 分组 | 固定资源 | 组件或使用方式 |
| --- | --- | --- |
| runtime | Azul Zulu JDK 8u504+1；Gradle 4.5.1/6.8；nvm 0.40.8；Node 10.24.1/14.21.3/18.20.8/22.23.3 | jdk、gradle、nvm；JDK 分架构，Gradle/nvm 通用；Node 10/14 x64，18/22 arm64/x64 |
| software | IDEA Community Open Source 2025.3.6.1；DBeaver CE 26.2.2；iTerm2 3.7.3 | idea、iterm2；DBeaver 维护者下载后手动安装 |
| plugins | 六个 IDEA 插件；固定 Oh My Zsh、zsh-autosuggestions、zsh-syntax-highlighting | IDEA 安装含六个插件；Oh My Zsh 使用 git、z 与两个外部插件 |

IDEA 插件为 Database Navigator 4.1.0.3、MyBatisX 1.7.6、GenerateAllSetter 2.8.5、GsonFormatPlus 1.6.1、Key Promoter X 2026.1.2、Lombok 253.28294.251。IDEA 2024 与 Node 16 已从新安装资源集合移除，已有对象不自动删除。Docker Desktop 仅登记[官方入口与许可](runtime-sources.md#docker-desktop仅登记暂不自动下载)，不下载。

固定版本、来源和支持范围见[运行环境来源](runtime-sources.md)、[IDEA/插件来源](plugin-sources.md)、[前端来源](frontend-sources.md)。资源下载与摘要通过不等于目标机器安装或业务项目构建通过。

## 源资源库与本地服务

完成[Python 安装与验证](../service-startup.md#部署前安装-python-3)，在实际服务器仓库根目录运行；Windows 将 python3 改为 py -3：

```bash
python3 server/manage.py start
```

start 先绑定端口，准备运行文件和全部清单资源，生成三个成员发布文件，并把本次包清单中的 `/resources/...` URL **只读映射到源资源库**。默认不生成 `dist/server/resources/` 副本；大包只需存一份。源库须保留以便校验、重新打包和本地下载服务读取。未知文件、旁置摘要及目录浏览不公开托管。

资源有固定摘要时用 catalog 中的值；官方未提供独立摘要且清单记为 `-` 的资源，首次下载生成同名 `.sha256` 本地记录，随后只检查是否变化。它是源库校验依据，不是上游签名或成员下载端点；打包时把确定摘要写进 TAR 内 resources.tsv。已固定摘要的文件不需要发布旁置摘要，源库已有历史记录保留。校验失败保留原文件，由维护者核对后移走异常内容，不为绕过检查修改摘要。

运行文件七项不计入 catalog，由独立的 schema 1 runtime-lock 管理。修改源码后构建/上传匹配运行文件是维护者工作，见[运行文件指南](../environment/runtime-release.md)。本地服务只读取匹配产物，不执行 Mac 二进制。

## 分组准备与只读校验

```bash
python3 server/manage.py prepare --dry-run
python3 server/manage.py prepare
python3 server/manage.py prepare --verify
python3 server/manage.py prepare --group runtime
python3 server/manage.py prepare --group software --arch arm64
python3 server/manage.py prepare --id mybatisx
python3 server/manage.py prepare --output /absolute/path/team-resources
```

默认 catalog/resources 在源库。自定义目录打包前复制清单：`cp resources/catalog.tsv /absolute/path/team-resources/catalog.tsv`；Windows 用 Copy-Item。`--group all|runtime|software|plugins` 与 `--arch all|arm64|x64|any` 同时筛选，arm64 筛选会包含 any，但不会包含 Node 10/14 x64。给 Apple Silicon 提供这两版时再准备 node10-macos-x64、node14-macos-x64，或使用全量清单；成员须已有 Rosetta。

--dry-run 不联网、不写文件；--verify 只校验已有文件，不下载/补记录。资源损坏保留报错；许可证、原始归档和源库首次下载记录须保留。系统原生服务器入口可传这些子命令，既有 Mac `tools/prepare-resources.sh` 也可使用。

## 部署副本与预览

本机 Python 服务无需复制资源：

```bash
python3 server/manage.py package --server "192.168.1.20:8080" --scheme http --output dist/server
python3 server/manage.py serve --directory dist/server --resources-dir resources --bind 0.0.0.0 --port 8080
```

需要上传到外部静态服务器时才显式使用：

```bash
python3 server/manage.py package --server "team-download.example:8080" --scheme http --with-resources --output dist/server
```

`--with-resources` 在输出目录复制所需原包，不另写资源 `.sha256`，不将资源塞入 TAR。上传三个成员发布文件和清单资源路径；静态服务须按同一白名单限制访问、关闭目录浏览。省略参数时不生成副本，既有副本保留。package 不联网；serve 先验证 schema 2 清单和文件，再按包内资源清单托管，源库参数优先于部署副本。详细规则见[分发指南](../distribution.md)。

preview 默认只监听 127.0.0.1:8081，并使用退出清理的临时目录，忽略正式 output 配置；只有显式 --output 才保留预览产物。它准备运行文件但不下载缺失软件资源，先 prepare。端口占用不改旧服务或发布文件。

## 成员安装与仅下载

成员下载 helper，运行 `bash devtool-helper.sh`，在同一安装页选择六组件与版本，Enter 预检并安装。全量默认 JDK 8、Gradle 4.5.1、nvm 和 Node 14.21.3、iTerm2、Oh My Zsh、IDEA/插件；安装页同样默认选14，其他版本仍可选。显式 all 才安装四版，首次或旧 default 失效时回退到14，有效 default 保留；单版（包括默认单14）设所选默认，none 仅配置 nvm、不改默认。应用在个人 `$HOME/Applications`；结果含实际版本、默认及切换指引，详见[环境指南](../environment/README.md)。

维护者仅下载 DBeaver 或插件时，在具有打包资源清单的工具目录运行 download-tools.sh，文件位于 `~/Downloads/team-java-env/` 相应子目录；原始插件 ZIP 从 IDEA 的 Install Plugin from Disk 安装，无需解压。下载完成不代表插件安装验证或实际功能通过。IDEA 冲突旧应用先按[卸载指南](../environment/cleanup.md)核对，不静默覆盖。

## 离线范围

本资源库解决 SDK/应用/插件获取，不包含业务 Maven/Gradle 依赖、JDBC 驱动和 MySQL 容器镜像。项目维护者须另行准备并验证真实构建、IDEA 同步和数据库连接；连接团队数据库不要求本地 MySQL，容器服务见[服务指南](../environment/services.md)。
