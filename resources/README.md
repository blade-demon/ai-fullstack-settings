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

当前清单共 14 项，包含两种 Mac 架构的 JDK 8、IDEA 2024 社区版、DBeaver，以及通用 Gradle 4.5.1 / 6.8 和六个免费插件。完整下载大小以实际文件为准。Docker 不在下载清单中。

## 已准备的文件

2026-10-06 已下载以下 13 个原始文件。新增 Gradle 6.8 本次仅登记到清单，目标文件为 `runtime/gradle/gradle-6.8-bin.zip`，尚未下载；需运行准备与校验命令后再分发。下载完成不代表已安装或通过业务项目运行验收。

| 软件 / 插件 | 版本 | 文件 |
| --- | --- | --- |
| Azul Zulu JDK 8 | 8u504+1 | [Apple Silicon](runtime/jdk/jdk8-macos-arm64.tar.gz) / [Intel](runtime/jdk/jdk8-macos-x64.tar.gz) |
| Gradle | 4.5.1 | [通用 ZIP](runtime/gradle/gradle-4.5.1-bin.zip) |
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
├── runtime/
│   ├── jdk/                 # JDK 8，两种 Mac 架构
│   └── gradle/              # Gradle 4.5.1、6.8（新增待下载）
├── software/
│   ├── idea/                # IDEA 2024.3.7.1 Community DMG
│   └── dbeaver/             # DBeaver Community 26.2.2 DMG
└── plugins/idea/            # 原始插件 ZIP，无需解压
```

下载器为每个资源保存同名 `.sha256`。有官方摘要时与官方值核对；没有官方摘要的插件仅记录本地文件摘要，用于后续检测文件是否变化，不能称为官方真实性认证。

首次分发时，使用 `tools/package.sh --with-resources` 将校验后的资源放入 `dist/server/resources/`。大包不进入启动 ZIP 或完整工具 ZIP。操作和来源详见[资源准备指南](../docs/resources/README.md)。这些安装包不包含业务项目的 Maven/Gradle 依赖缓存、JDBC 驱动缓存或 MySQL 容器镜像。
