# 本地资源目录

这里保存团队环境所需的原始安装包和插件 ZIP。[catalog.tsv](catalog.tsv) 固定版本、架构、官方来源和可取得的上游 SHA-256；文件是否已准备好，以校验命令的结果为准。

在仓库根目录执行：

```bash
# 查看待准备的资源，不联网
bash tools/prepare-resources.sh --dry-run

# 下载清单内全部资源；已有且校验通过的文件会复用
bash tools/prepare-resources.sh

# 只检查现有文件，不下载
bash tools/prepare-resources.sh --verify
```

当前清单共 24 项，原有 14 项包含两种 Mac 架构的 JDK 8、IDEA 2024 社区版、DBeaver，以及通用 Gradle 4.5.1 / 6.8 和六个免费插件。完整下载大小以实际文件为准。Docker 不在下载清单中。

Go TUI 的四个文件位于 `tui/`，卸载工具的三个文件位于 `cleanup/`；它们不在 24 项 SDK、软件和插件安装资源清单内。`runtime-lock.json` 固定这七个运行文件对应的 ZIP、下载地址、摘要、大小和源码版本。

下载服务器正常拉取仓库后继续执行 `python3 server/manage.py start` 即可；Windows 使用 `py -3`。有效本地运行文件会复用；缺失、损坏或过期时自动从锁定 GitHub Release 下载并校验，不需要手动传 ZIP 或安装 Go、PyInstaller。首次缺少文件需访问 GitHub 或镜像，有效缓存可离线复用。单独操作可运行：

```bash
python3 server/manage.py prepare-runtimes
python3 server/manage.py prepare-runtimes --offline
python3 server/manage.py prepare-runtimes --runtime-base-url "http://192.168.1.20:8088/runtime-release"
```

`--offline` 只读校验；镜像参数指向包含 `team-dev-env-runtimes.zip` 的目录，也可通过 `server/config.json` 的 `runtime_base_url` 设置，仍须满足原锁摘要。`package` 只校验和打包，不联网；`start` 会先准备运行文件，再准备 24 项安装资源。上述 Bash 资源准备脚本只处理安装资源，不生成这些预构建运行文件。

修改 Go 或卸载源码时，维护者在 Mac 按[TUI 构建说明](../docs/environment/tui.md#构建与分发)和[卸载构建指南](../docs/environment/cleanup.md#维护者构建成员卸载工具)准备产物，生成并上传匹配的 ZIP，再将锁与源码配套提交。完整流程见[运行文件发布指南](../docs/environment/runtime-release.md)，目前没有 CI 自动构建或上传。手动复制七个产物仅作为离线部署选项。

新增前端环境的 10 个包已经准备到 `frontend/` 并验证固定摘要；版本、架构及来源见[前端资源记录](../docs/resources/frontend-sources.md)。

## 已准备的文件

2026-10-06 已下载原有 13 个文件，2026-10-07 补齐 Gradle 6.8 并通过官方固定 SHA-256 校验；以下共 14 个原始文件，分发时仍会核验。下载完成不代表已安装或通过业务项目运行验收。

| 软件 / 插件 | 版本 | 文件 |
| --- | --- | --- |
| Azul Zulu JDK 8 | 8u504+1 | [Apple Silicon](runtime/jdk/jdk8-macos-arm64.tar.gz) / [Intel](runtime/jdk/jdk8-macos-x64.tar.gz) |
| Gradle | 4.5.1 / 6.8 | [4.5.1 ZIP](runtime/gradle/gradle-4.5.1-bin.zip) / [6.8 ZIP](runtime/gradle/gradle-6.8-bin.zip) |
| IntelliJ IDEA Community | 2024.3.7.1 | [Apple Silicon](software/idea/ideaIC-2024.3.7.1-aarch64.dmg) / [Intel](software/idea/ideaIC-2024.3.7.1.dmg) |
| DBeaver Community | 26.2.2 | [Apple Silicon](software/dbeaver/dbeaver-ce-26.2.2-macos-aarch64.dmg) / [Intel](software/dbeaver/dbeaver-ce-26.2.2-macos-x86_64.dmg) |
| Database Navigator | 4.1.0.3 | [插件 ZIP](plugins/idea/DBN-4.1.0.3.zip) |
| MyBatisX | 1.7.6 | [插件 ZIP](plugins/idea/MybatisX-1.7.6.zip) |
| GenerateAllSetter | 2.8.5 | [插件 ZIP](plugins/idea/GenerateAllSetter-2.8.5.zip) |
| GsonFormatPlus | 1.6.1 | [插件 ZIP](plugins/idea/GsonFormatPlus-1.6.1.zip) |
| Key Promoter X | 2026.1.2 | [插件 ZIP](plugins/idea/Key_Promoter_X-2026.1.2.zip) |
| Lombok | 243.28141.18 | [插件 ZIP](plugins/idea/lombok-243.28141.18.zip) |

```text
resources/
├── catalog.tsv
├── runtime-lock.json       # Git 跟踪的运行文件版本、下载地址、摘要与大小
├── frontend/               # nvm、Node三版本、iTerm2、Oh My Zsh及插件
├── tui/                    # Go双架构TUI、manifest与许可
├── cleanup/                # Mac 预构建的双架构卸载工具、manifest 与第三方许可
├── runtime/
│   ├── jdk/                 # JDK 8，两种 Mac 架构
│   └── gradle/              # Gradle 4.5.1、6.8
├── software/
│   ├── idea/                # IDEA 2024.3.7.1 Community DMG
│   └── dbeaver/             # DBeaver Community 26.2.2 DMG
└── plugins/idea/            # 原始插件 ZIP，无需解压
```

下载器为每个资源保存同名 `.sha256`。有官方摘要时与官方值核对；没有官方摘要的插件仅记录本地文件摘要，用于后续检测文件是否变化，不能称为官方真实性认证。

正常分发使用 `server/manage.py start` 自动准备并打包；高级流程可用 `server/manage.py package --with-resources` 将已校验的安装资源放入 `dist/server/resources/`，Mac 的 `tools/package.sh --with-resources` 继续可用。大包不进入启动 ZIP 或完整工具 ZIP。拉取源码不会更新发布目录，须重新 `start` 或 `package`，并核对输出版本与 `release.json`。操作和来源详见[资源准备指南](../docs/resources/README.md)。这些安装包不包含业务项目的 Maven/Gradle 依赖缓存、JDBC 驱动缓存或 MySQL 容器镜像。
