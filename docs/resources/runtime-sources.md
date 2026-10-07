# 运行环境与桌面工具的官方资源来源

首次核对日期：2026-10-06；2026-10-07 补充 Gradle 6.8。目标平台为 macOS Apple Silicon（arm64/aarch64）和 Intel（x64/x86_64）。JDK 固定为 Java 8，Gradle 资源包括 4.5.1、6.8，分别固定到下文所列版本。本文只核对官方网页、元数据、小型校验文件与既有安装包的 HTTP HEAD 响应；**本次研究没有下载、安装或运行任何大型安装包**。下载后的完整文件仍须另行计算 SHA-256。

所有安装包链接均由官方 API、官方归档目录或官方发布说明取得。2026-10-06 登记的资源已跟随重定向确认最终 HEAD 状态为 200；2026-10-07 新增资源仅核对官方元数据与校验值，未重新下载或检查安装包 HEAD。不要把 GitHub 最终生成的带时效签名 URL 存进清单；使用本文固定版本入口。

## JDK 8：Azul Zulu CA

两种架构统一选择 **OpenJDK 8u504+1 / Azul Zulu 8.96.0.205，GA、PSU、JDK、不含 JavaFX**。CA 是 Azul 官方提供的免费发行渠道；需要商业服务时另选 SA。来源：[安装渠道说明](https://docs.azul.com/core/install/index)、[官方 Metadata API 文档](https://api.azul.com/metadata/v1/docs/swagger)。

| 架构 | 固定版本官方下载 | SHA-256 | HEAD 文件字节数 |
| --- | --- | --- | ---: |
| arm64 | [zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64.tar.gz](https://cdn.azul.com/zulu/bin/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64.tar.gz) | `58bb3c08f2aa63d9743cf31899fa4b8c6c9effefce9479e7288c26621c3bb21b` | 103714410 |
| x64 | [zulu8.96.0.205-ca-jdk8.0.504-macosx_x64.tar.gz](https://cdn.azul.com/zulu/bin/zulu8.96.0.205-ca-jdk8.0.504-macosx_x64.tar.gz) | `e35bc8a4401193aa670146762bbad132bf0651fee5e3f16acbb3a5db0e0b0cff` | 106151769 |

版本、包类型、架构、下载 URL 和 SHA-256 分别来自 [arm64 元数据](https://api.azul.com/metadata/v1/zulu/packages/16811ca3-e48b-459d-abc4-f6b273023a54)与 [x64 元数据](https://api.azul.com/metadata/v1/zulu/packages/8bcaa40f-f617-4040-b56e-40df6961f7b8)。注意 API 的 `size` 分别为 103714000 和 106152000，与 HEAD 的精确字节数略有差异；清单采用 HEAD 实值，不应用 API 近似值拒绝下载。

Azul 当前支持矩阵对这两种 macOS 架构列出 **macOS 14+**；这属于厂商当前支持范围，不能由此断言低版本必然无法启动，也不能承诺低版本受支持。按当前范围准备团队环境，并在目标电脑实际运行 `java -version` 与 `javac -version`。来源：[2026 年 8 月及 Java 27 GA 支持矩阵](https://docs.azul.com/core/supported-platforms)。

本仓库安装脚本使用 tar.gz，下载后保持内容不变，分别保存为 `resources/runtime/jdk/jdk8-macos-arm64.tar.gz` 和 `resources/runtime/jdk/jdk8-macos-x64.tar.gz`。SHA-256 不因重命名改变。文件内部目录结构仍需下载后检查。

## Gradle 4.5.1

官方下载：[gradle-4.5.1-bin.zip](https://services.gradle.org/distributions/gradle-4.5.1-bin.zip)。官方另一个分发入口 [downloads.gradle.org](https://downloads.gradle.org/distributions/gradle-4.5.1-bin.zip) 当前重定向至 [Gradle 官方 GitHub 固定发布附件](https://github.com/gradle/gradle-distributions/releases/download/v4.5.1/gradle-4.5.1-bin.zip)。HEAD 精确大小为 **72424144 字节**。

SHA-256：`3e2ea0d8b96605b7c528768f646e0975bd9822f06df1f04a64fd279b1a17805e`。已对照 [官方校验文件](https://services.gradle.org/distributions/gradle-4.5.1-bin.zip.sha256)和 [官方历史校验清单](https://gradle.org/release-checksums/)。保存为 `resources/runtime/gradle/gradle-4.5.1-bin.zip`，供两种架构共用。

[4.5.1 安装文档](https://docs.gradle.org/4.5.1/userguide/installation.html)要求最低 Java 7，已对照 [v4.5.1 官方文档源码](https://github.com/gradle/gradle/blob/v4.5.1/subprojects/docs/src/docs/userguide/installation.adoc)。结合[官方 Java 运行兼容矩阵](https://docs.gradle.org/current/userguide/compatibility.html#java_runtime)中 Java 9 从 Gradle 4.3 支持、Java 10 从 4.7 支持，可确定 **4.5.1 的受支持 Java 运行范围为 7–9**；本项目使用 JDK 8。不能把旧文档的最低版本描述理解为支持任意新 JDK。[Gradle 6.9 发布说明](https://docs.gradle.org/6.9/release-notes.html#native-support-for-apple-silicon)才明确加入完整的 Apple Silicon 原生功能支持，并说明早期版本使用 ARM JDK 时部分原生功能不可用。因此，4.5.1 的同一 ZIP 可作为两架构候选资源，但 **JDK 8 ARM + Gradle 4.5.1 + 业务项目** 的运行组合必须实测；取得安装包和 SHA-256 不等于完成构建验证。Gradle 4.5.1 保持独立资源，不自动升级。

## Gradle 6.8

固定为 **6.8**，不替换为 6.8.1、6.8.2 或 6.8.3。官方下载：[gradle-6.8-bin.zip](https://services.gradle.org/distributions/gradle-6.8-bin.zip)，保存为 `resources/runtime/gradle/gradle-6.8-bin.zip`，供两种架构共用。

SHA-256：`e2774e6fb77c43657decde25542dea710aafd78c4022d19b196e7e78d79d8c6c`。已同时对照[官方校验文件](https://services.gradle.org/distributions/gradle-6.8-bin.zip.sha256)与[官方历史校验清单的 6.8 条目](https://gradle.org/release-checksums/)。本次没有下载 ZIP 或核对 HEAD 大小。

[v6.8.0 官方兼容文档源码](https://github.com/gradle/gradle/blob/v6.8.0/subprojects/docs/src/docs/userguide/compatibility.adoc)明确限定 **Java 8–15**，不支持 Java 16 及之后版本；该源码标签对应发布版本 6.8。结合[当前官方兼容矩阵](https://docs.gradle.org/current/userguide/compatibility.html#java_runtime)，**JDK 8 在 Gradle 4.5.1 与 6.8 的受支持 Java 运行范围内**。本项目两版 Gradle 均使用 JDK 8。

Gradle 6.8 同样早于完整支持 Apple Silicon 的 6.9；使用 ARM JDK 时，部分原生功能会被禁用。保留用户指定的 6.8，并在目标电脑验证构建，不因资源存在而宣称已完成运行兼容验证。来源：[6.9 的 Apple Silicon 原生支持说明](https://docs.gradle.org/6.9/release-notes.html#native-support-for-apple-silicon)。

## DBeaver Community 26.2.2

官方当前版本为 **26.2.2，发布于 2026-10-04**。选择 Community 免费开源版，两种 DMG 均来自 [官方固定版本归档目录](https://dbeaver.io/files/26.2.2/)，当前下载会跳转到 DBeaver 官方 GitHub 发布附件。

| 架构 | 固定版本官方下载 | SHA-256 | HEAD 文件字节数 |
| --- | --- | --- | ---: |
| arm64 | [dbeaver-ce-26.2.2-macos-aarch64.dmg](https://dbeaver.io/files/26.2.2/dbeaver-ce-26.2.2-macos-aarch64.dmg) | `7f47579bc583571ca0ccef9fdce7d6cc56f84b74844e4e700ab7a46d1e501ec5` | 122907891 |
| x64 | [dbeaver-ce-26.2.2-macos-x86_64.dmg](https://dbeaver.io/files/26.2.2/dbeaver-ce-26.2.2-macos-x86_64.dmg) | `e8d60c79a9e0191ede23d33b4f6c21385da3474d8aa34c63bae0a553a0c510de` | 124276362 |

SHA-256 来源：[arm64 校验文件](https://dbeaver.io/files/26.2.2/checksum/dbeaver-ce-26.2.2-macos-aarch64.dmg.sha256)、[x64 校验文件](https://dbeaver.io/files/26.2.2/checksum/dbeaver-ce-26.2.2-macos-x86_64.dmg.sha256)。归档网页显示的 117.21 MB / 118.52 MB 是显示用近似数，清单采用 HEAD 字节数。

[官方下载安装页](https://dbeaver.io/download/)列出 **macOS 11+**，并说明当前 DBeaver 需要 Java 25+、发行包包含 OpenJDK 25。保留其自带运行时，不要强制让 DBeaver 使用项目 JDK 8。许可证原文见 [DBeaver Community License](https://dbeaver.io/product/dbeaver_license.txt)。

## Docker Desktop：仅登记，暂不自动下载

官方入口：[macOS 安装指南](https://docs.docker.com/desktop/setup/install/mac-install/)、[发布说明与校验文件](https://docs.docker.com/desktop/release-notes/)。核对时最新发布说明为 **4.94.0，2026-10-05，build 241994**。下表固定到该 build，仅用于以后明确选择后获取；本次未下载 Docker DMG。

| 架构 | 官方固定 build 下载 | SHA-256 | HEAD 文件字节数 |
| --- | --- | --- | ---: |
| arm64 | [Docker 4.94.0 Apple Silicon](https://desktop.docker.com/mac/main/arm64/241994/Docker.dmg) | `02147e4d559ff41e1d9d7be63a554101340237064c7b6df234548aa111ebf04c` | 587631519 |
| x64 | [Docker 4.94.0 Intel](https://desktop.docker.com/mac/main/amd64/241994/Docker.dmg) | `44a9c8524c6f5cc6ba51cec7fd6343b2a744ff4cb5126f7d3d5b6f4da06fd905` | 645705457 |

SHA-256 来源：[arm64 checksums.txt](https://desktop.docker.com/mac/main/arm64/241994/checksums.txt)、[amd64 checksums.txt](https://desktop.docker.com/mac/main/amd64/241994/checksums.txt)。两包总计 1233336976 字节，约 1.23 GB（十进制）。官方说明超过最新发布六个月的旧版可能不再提供下载，所以固定 URL 也不能被视为永久托管承诺。来源：[Docker 发布说明](https://docs.docker.com/desktop/release-notes/)。

系统要求为当前及前两个 macOS 主版本、至少 4 GB RAM。Apple Silicon 上 Rosetta 2 不再是严格前提，但某些 Darwin/AMD64 命令工具仍需要它。具体版本支持范围应在安装时复核。来源：[Docker macOS 安装指南](https://docs.docker.com/desktop/setup/install/mac-install/)。

免费使用范围包括个人、教育、非商业开源项目，以及员工少于 250 人且年收入低于 1000 万美元的小企业；其他专业用途和政府机构需要付费订阅。团队应按所在组织确认适用订阅，安装时由有权限的人接受协议，不在脚本中自动代为接受。来源：[官方许可摘要](https://docs.docker.com/desktop/setup/install/mac-install/#install-interactively)、[Docker Subscription Service Agreement](https://www.docker.com/legal/docker-subscription-service-agreement/)。

## 可转入资源清单的结构化数据

顶层 `checked_at` 与 `verification` 是既有资源的默认核对记录；新增资源通过条目内同名字段覆盖。`official_metadata_and_head` 表示官方元数据、官方校验值与 HEAD 已核对；`official_metadata_and_checksum` 表示只核对官方元数据与校验值。`downloaded` 均为本次研究任务的状态，不代表其他任务是否随后下载。`sha256` 是官方预期值，下载器需要重新计算实际文件摘要。Docker 必须保留 `download_policy: manual`。

```json
{
  "checked_at": "2026-10-06",
  "verification": "official_metadata_and_head",
  "artifacts": [
    {
      "id": "jdk8-macos-arm64",
      "product": "Azul Zulu CA JDK",
      "version": "8u504+1",
      "vendor_version": "8.96.0.205",
      "os": "macos",
      "arch": "arm64",
      "url": "https://cdn.azul.com/zulu/bin/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64.tar.gz",
      "sha256": "58bb3c08f2aa63d9743cf31899fa4b8c6c9effefce9479e7288c26621c3bb21b",
      "size_bytes": 103714410,
      "metadata_url": "https://api.azul.com/metadata/v1/zulu/packages/16811ca3-e48b-459d-abc4-f6b273023a54",
      "downloaded": false
    },
    {
      "id": "jdk8-macos-x64",
      "product": "Azul Zulu CA JDK",
      "version": "8u504+1",
      "vendor_version": "8.96.0.205",
      "os": "macos",
      "arch": "x64",
      "url": "https://cdn.azul.com/zulu/bin/zulu8.96.0.205-ca-jdk8.0.504-macosx_x64.tar.gz",
      "sha256": "e35bc8a4401193aa670146762bbad132bf0651fee5e3f16acbb3a5db0e0b0cff",
      "size_bytes": 106151769,
      "metadata_url": "https://api.azul.com/metadata/v1/zulu/packages/8bcaa40f-f617-4040-b56e-40df6961f7b8",
      "downloaded": false
    },
    {
      "id": "gradle-4.5.1-bin",
      "product": "Gradle",
      "version": "4.5.1",
      "os": "any",
      "arch": "any",
      "url": "https://services.gradle.org/distributions/gradle-4.5.1-bin.zip",
      "sha256": "3e2ea0d8b96605b7c528768f646e0975bd9822f06df1f04a64fd279b1a17805e",
      "size_bytes": 72424144,
      "checksum_url": "https://services.gradle.org/distributions/gradle-4.5.1-bin.zip.sha256",
      "downloaded": false
    },
    {
      "id": "gradle-6.8-bin",
      "product": "Gradle",
      "version": "6.8",
      "os": "any",
      "arch": "any",
      "url": "https://services.gradle.org/distributions/gradle-6.8-bin.zip",
      "sha256": "e2774e6fb77c43657decde25542dea710aafd78c4022d19b196e7e78d79d8c6c",
      "checksum_url": "https://services.gradle.org/distributions/gradle-6.8-bin.zip.sha256",
      "checked_at": "2026-10-07",
      "verification": "official_metadata_and_checksum",
      "downloaded": false
    },
    {
      "id": "dbeaver-ce-macos-arm64",
      "product": "DBeaver Community",
      "version": "26.2.2",
      "os": "macos",
      "arch": "arm64",
      "url": "https://dbeaver.io/files/26.2.2/dbeaver-ce-26.2.2-macos-aarch64.dmg",
      "sha256": "7f47579bc583571ca0ccef9fdce7d6cc56f84b74844e4e700ab7a46d1e501ec5",
      "size_bytes": 122907891,
      "checksum_url": "https://dbeaver.io/files/26.2.2/checksum/dbeaver-ce-26.2.2-macos-aarch64.dmg.sha256",
      "downloaded": false
    },
    {
      "id": "dbeaver-ce-macos-x64",
      "product": "DBeaver Community",
      "version": "26.2.2",
      "os": "macos",
      "arch": "x64",
      "url": "https://dbeaver.io/files/26.2.2/dbeaver-ce-26.2.2-macos-x86_64.dmg",
      "sha256": "e8d60c79a9e0191ede23d33b4f6c21385da3474d8aa34c63bae0a553a0c510de",
      "size_bytes": 124276362,
      "checksum_url": "https://dbeaver.io/files/26.2.2/checksum/dbeaver-ce-26.2.2-macos-x86_64.dmg.sha256",
      "downloaded": false
    },
    {
      "id": "docker-desktop-macos-arm64",
      "product": "Docker Desktop",
      "version": "4.94.0",
      "build": "241994",
      "os": "macos",
      "arch": "arm64",
      "url": "https://desktop.docker.com/mac/main/arm64/241994/Docker.dmg",
      "sha256": "02147e4d559ff41e1d9d7be63a554101340237064c7b6df234548aa111ebf04c",
      "size_bytes": 587631519,
      "checksum_url": "https://desktop.docker.com/mac/main/arm64/241994/checksums.txt",
      "download_policy": "manual",
      "downloaded": false
    },
    {
      "id": "docker-desktop-macos-x64",
      "product": "Docker Desktop",
      "version": "4.94.0",
      "build": "241994",
      "os": "macos",
      "arch": "x64",
      "url": "https://desktop.docker.com/mac/main/amd64/241994/Docker.dmg",
      "sha256": "44a9c8524c6f5cc6ba51cec7fd6343b2a744ff4cb5126f7d3d5b6f4da06fd905",
      "size_bytes": 645705457,
      "checksum_url": "https://desktop.docker.com/mac/main/amd64/241994/checksums.txt",
      "download_policy": "manual",
      "downloaded": false
    }
  ]
}
```
