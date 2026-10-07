# 运行文件自动下载与维护者发布

下载服务器只需 Python 3.8+ 标准库。Windows 或 macOS 正常拉取仓库后，继续执行原来的 `server/manage.py start`，或双击原服务器启动入口即可。服务器优先复用与当前源码匹配的本地产物；缺失、损坏或过期时，按 Git 跟踪的 `resources/runtime-lock.json` 下载匹配运行文件，不在服务器编译 Go，也不要求人工传入 ZIP。

成员工具仍只面向 macOS。运行文件包括 Go TUI 的 arm64 / amd64 程序和自带 Python 的 universal2 卸载工具；Windows 服务器只校验和打包，不执行这些程序。

## 下载服务器的日常操作

在仓库根目录运行；Windows 将 `python3` 换成 `py -3`：

```bash
# 原一键启动：先取得端口，再准备运行文件与安装资源，打包并提供下载
python3 server/manage.py start

# 只准备界面和卸载运行文件，不下载 SDK 或启动服务
python3 server/manage.py prepare-runtimes

# 只读校验本地运行文件，不联网、不写入
python3 server/manage.py prepare-runtimes --offline
```

首次缺少运行文件时，服务器需要能访问锁定的 GitHub Release 或团队镜像；已校验且与当前源码匹配的本地缓存无需联网。`--offline` 只用于 `prepare-runtimes`，文件缺失、损坏或过期时返回失败。完全离线执行 `start` 还需要 24 项 SDK、软件和插件安装资源已准备齐全，可用 `python3 server/manage.py prepare --verify` 预检。

`start` 成功绑定端口后，先补齐运行文件，再处理 SDK 等安装资源；`preview` 同样先补齐运行文件，但只校验已有安装资源，不下载缺失 SDK。`package` 始终只校验和打包，不联网。运行文件固定保存在仓库 `resources/tui/` 和 `resources/cleanup/`，不随 `--resources-dir` 改变。

**`git pull` 更新源码，不等于更新发布目录。** 日常更新应停止自己管理的旧服务，再运行原 `start`。端口占用时，本次没有更新安装包，已有地址可能仍提供旧版本；脚本不会结束占用进程或修改旧发布目录。完整启动与版本确认见[服务启动指南](../service-startup.md)。

## 内网镜像与离线复制

把锁中对应的 `team-dev-env-runtimes.zip` 原样放到团队 HTTP 或 HTTPS 目录，例如：

```text
http://192.168.1.20:8088/runtime-release/team-dev-env-runtimes.zip
```

传入它所在的**目录 URL**，不要传 ZIP 文件 URL：

```bash
python3 server/manage.py start --runtime-base-url "http://192.168.1.20:8088/runtime-release"
python3 server/manage.py prepare-runtimes --runtime-base-url "http://192.168.1.20:8088/runtime-release"
```

也可在已有 `server/config.json` 中加入：

```json
{
  "runtime_base_url": "http://192.168.1.20:8088/runtime-release"
}
```

命令行参数优先于配置文件；未指定时使用锁中的 GitHub Release URL。镜像只替换下载来源，不能放宽锁定归档和七个成员的 SHA-256、大小、架构及源码一致性要求。下载、校验或替换失败时保留现有文件；不要通过修改锁的摘要接受来历不明的 ZIP。

无法联网的服务器也可选择从可信维护者复制已校验的 `resources/tui/` 四文件和 `resources/cleanup/` 三文件，保留原相对路径，并复制配套源码和锁。随后运行 `prepare-runtimes --offline`。手动复制是离线部署选项，不是正常联网部署的必要步骤。

## 维护者更新运行文件

只有 Go 源码、Go 测试、`go.mod` / `go.sum` 或 `tools/uninstall_java_gradle.py` 变化后，才需要更新相应运行文件。其他成员脚本变化仍要重新生成成员发布目录，但不一定需要新运行文件 Release。目前没有 CI 自动构建或上传，以下步骤由维护者执行。

### 1. 在 Mac 准备并校验两套产物

按 [Go TUI 构建指南](tui.md#构建与分发)和[卸载构建指南](cleanup.md#维护者构建成员卸载工具)准备所需构建环境，重建有源码变化的产物，并确认两套产物都与当前源码匹配。示例使用已有 Go 和已按卸载指南创建的固定版本虚拟环境：

```bash
python3 tools/build-tui.py --go /absolute/path/to/go
/tmp/team-cleanup-build/bin/python tools/build-cleanup.py
python3 tools/build-tui.py --verify-only
python3 tools/build-cleanup.py --verify-only
```

源码摘要以 UTF-8 去 BOM、LF 换行规范化；Go 摘要还包含排序后的相对路径，兼容 Windows Git 的 CRLF 检出。发布包只能包含以下七个仓库相对路径，不包含目录项或 README：

```text
resources/tui/team-dev-env-arm64
resources/tui/team-dev-env-amd64
resources/tui/manifest.json
resources/tui/THIRD_PARTY_NOTICES.txt
resources/cleanup/cleanup-macos-universal2
resources/cleanup/manifest.json
resources/cleanup/THIRD_PARTY_NOTICES.txt
```

### 2. 生成 ZIP 与版本锁

```bash
python3 tools/release-runtimes.py
python3 tools/release-runtimes.py --verify-only
```

生成器仅使用标准库，不构建、不联网、不上传。它先校验两套本地产物，生成固定时间、排序成员和固定权限的确定性 ZIP，再复核源码及运行文件未发生变化。二进制权限为 `755`，清单和许可为 `644`。缺失、损坏或过期产物会在替换发布文件与锁之前失败；写入或最终复核失败会回滚已替换文件。

默认输出：

```text
dist/runtime-release/
├── team-dev-env-runtimes.zip
├── team-dev-env-runtimes.zip.sha256
└── release-notes.md
resources/runtime-lock.json
```

锁的 `schema` 为 `1`，包含两个源码 SHA-256、ZIP 的 URL / SHA-256 / 字节数，以及七个成员各自的 SHA-256 / 字节数。运行文件版本为 `runtimes-<ZIP SHA-256 前 16 位>`，同一组文件重复生成结果一致；默认下载地址位于 `blade-demon/ai-fullstack-settings` 的同名 GitHub Release。

`--output` 可指定发布文件输出目录，`--lock` 可指定锁路径，`--repository owner/repo` 可指定自己的 GitHub 仓库。使用自定义路径或仓库后，`--verify-only` 须使用同一组参数；它只校验既有包、锁与本地源码，不写入文件。实际部署仍读取仓库中的 `resources/runtime-lock.json`。

### 3. 提交配套源码和锁，上传匹配 Release

检查生成的中文发布说明、锁及源码变更，将相关源码与 `resources/runtime-lock.json` 作为同一变更提交并正常推送到发布仓库。生成的二进制和 ZIP 不直接提交到 Git。确认当前提交包含本次配套源码与锁后，在已登录且具有仓库发布权限的 GitHub CLI 环境执行：

```bash
release_id="$(python3 -c 'import json; print(json.load(open("resources/runtime-lock.json", encoding="utf-8"))["release"])')"
release_commit="$(git rev-parse HEAD)"

gh release create "$release_id" \
  dist/runtime-release/team-dev-env-runtimes.zip \
  dist/runtime-release/team-dev-env-runtimes.zip.sha256 \
  --repo blade-demon/ai-fullstack-settings \
  --target "$release_commit" \
  --title "$release_id" \
  --notes-file dist/runtime-release/release-notes.md
```

Release 名称必须取自本次生成的锁，不手填猜测版本；`--target` 指向已推送的配套提交。若使用 `--repository`，上面的 `--repo` 也要保持一致。该命令上传 ZIP、摘要文件，并把生成的中文说明作为 Release 正文。

同名版本已经存在时，先核对远端资产与锁是否完全一致；一致则复用，不重新创建或覆盖资产。不一致时停止并检查来源，不能通过重写标签或替换同名版本资产修补。让下载服务器拉取该变更前，应完成对应 Release 上传并确认锁中 URL 可下载，否则首次缺少运行文件的启动会失败。

在另一份尚未缓存运行文件、且源码与锁配套的检出目录中执行 `prepare-runtimes`，确认真实下载和校验通过，再执行 `prepare-runtimes --offline` 确认本地可复用。已有有效本地产物时会直接复用，因此不能用它证明远端资产可下载。

## 确认成员实际获得的版本

运行文件 Release 的 `runtimes-…` 用于下载预构建程序；成员下载目录使用另一个实际发布版本：`go-tui-<dev-env/team-dev-env.tar.gz 的 SHA-256 前 12 位>`。

`start` 完成三阶段后显示这个 Go TUI 版本、`start.zip?v=版本` 和 `/release.json` 链接。`release.json` 记录 `interface=go-tui`、发布时间、两个运行文件源码摘要和六个成员发布文件的 SHA-256 / 大小。`serve` 启动前验证这份信息与实际文件，拒绝缺少新版清单的旧包或损坏包；完整有效的历史包仍可托管，显示其自身版本，不冒充最新源码。

因此，更新后应核对本次就绪输出与 HTTP `/release.json`，再给成员新的下载链接。仅看 `git pull` 成功、某个端口仍能访问，或已有文件仍在磁盘上，都不能证明新版已发布。
