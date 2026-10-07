# IDEA 2024 与离线插件来源核验

## 新增 Lombok

2026-10-06 将 Lombok 纳入默认插件清单。使用 JetBrains 官方按 build 下载接口传入 `IC-243.28141.41`，解析到以下 stable 版本，已下载官方原包并读取内部 `META-INF/plugin.xml`：

| 插件 | 固定版本 / updateId | 声明的兼容 build | 必需依赖 | 官方原包 |
| --- | --- | --- | --- | --- |
| Lombok | `243.28141.18` / `854391` | `243.28141 — 243.*` | `com.intellij.modules.lang`、`com.intellij.modules.platform`、`com.intellij.modules.java` | [lombok-243.28141.18.zip](https://plugins.jetbrains.com/files/6317/854391/lombok-243.28141.18.zip) |

ZIP 为 494873 字节，唯一条目为 `lombok/lib/lombok.jar`；XML ID 使用历史拼写 `Lombook Plugin`。描述文件使用旧式 `<depends>`，无额外必需插件及新式 `<dependencies>` 子元素，兼容当前自动安装器。官方 Marketplace 标记 `pricingModel=FREE`，许可链接指向 [JetBrains User Agreement](https://www.jetbrains.com/legal/docs/toolbox/user.html)；归档未附独立 LICENSE/NOTICE 文件，不将其标记为 Apache 2.0。

来源：[按 build 下载接口](https://plugins.jetbrains.com/pluginManager?action=download&id=Lombook%20Plugin&build=IC-243.28141.41)、[指定更新](https://plugins.jetbrains.com/api/updates/854391)、[插件详情](https://plugins.jetbrains.com/api/plugins/6317)、[版本页](https://plugins.jetbrains.com/plugin/6317-lombok/versions/stable/854391)。

ZIP 和内部 JAR 完整性检查通过，本地计算的 SHA-256 为：

```text
cfd5f5dea4cfff7291219f143a53941f12f85fecb55f62d7f36ff61f0e2e8290  lombok-243.28141.18.zip
```

该摘要来自实际下载文件，不是官方独立公布的摘要。IDE 插件版本与业务项目的 Lombok 库版本分别管理，安装、启用、注解处理和项目验收步骤见 [IDE 指南](../environment/ide.md#lombok-安装与启用步骤)。此次核验未在真实 IDEA 中验收编辑器功能。

## 新增 GsonFormatPlus 与 Key Promoter X

2026-10-06 根据团队选择追加两款免费插件，已下载并读取 ZIP 内的 `plugin.xml`：

| 插件 | 固定版本 / updateId | 声明的最低 IDEA build | 平台依赖 | 官方原包 |
| --- | --- | --- | --- | --- |
| GsonFormatPlus | 1.6.1 / 115983 | 135.121，无声明上限 | `com.intellij.modules.java` | [GsonFormatPlus.zip](https://plugins.jetbrains.com/files/14949/115983/GsonFormatPlus.zip) |
| Key Promoter X | 2026.1.2 / 1098878 | 241，无声明上限 | `com.intellij.modules.lang` | [Key_Promoter_X-2026.1.2.zip](https://plugins.jetbrains.com/files/9792/1098878/Key_Promoter_X-2026.1.2.zip) |

两者声明的范围覆盖目标 `IC-243.28141.41`，依赖均为 IDEA 平台模块。版本元数据：[GsonFormatPlus](https://plugins.jetbrains.com/api/updates/115983)、[Key Promoter X](https://plugins.jetbrains.com/api/updates/1098878)。GsonFormatPlus 的本地文件重命名为 `GsonFormatPlus-1.6.1.zip`，文件内容保持原样。

已检查 ZIP 完整性，并记录以下本地 SHA-256（不是官方独立公布的摘要）：

```text
36e98bbfbf6900704e87a8eea99635b076c49ae69ebca058e77f0fd3c0f6f250  GsonFormatPlus-1.6.1.zip
dd76969715fb8d1d2e1f1fee4e9961c8f9b0d49f835a2c7a7d0c1e71709fae4c  Key_Promoter_X-2026.1.2.zip
```

成员可通过菜单 `5` 安装全部 IDEA 插件；需要手动安装时，由维护者通过 `download-tools.sh` 下载原始 ZIP，再使用 IDEA 的 `Install Plugin from Disk` 安装并按提示重启。本次来源核验未对用户正在使用的 IDEA 执行安装或功能验收。

核验日期：2026-10-06。目标：macOS Apple Silicon / Intel，IntelliJ IDEA **Community Edition 2024.3.7.1，build `IC-243.28141.41`**。本文记录官方来源和静态兼容性；不表示已经在 IDEA 中安装并验收全部插件。

## IDEA 安装包

JetBrains 产品发行 API 的 `IIC` / `type=release` 记录中，2024.3 分支最新正式版为 `2024.3.7.1`，发行日期 `2026-04-30`，build `243.28141.41`。固定这一版本；不要使用会滚动到新大版本的“latest”地址。来源：[官方发行 API](https://data.services.jetbrains.com/products/releases?code=IIC&type=release)、[版本说明](https://youtrack.jetbrains.com/articles/IDEA-A-2100662666/IntelliJ-IDEA-2024.3.7.1-243.28141.41-build-Release-Notes)。

| 平台 | 文件与官方直链 | 字节数 | 官方校验文件 |
| --- | --- | ---: | --- |
| Apple Silicon / arm64 | [ideaIC-2024.3.7.1-aarch64.dmg](https://download.jetbrains.com/idea/ideaIC-2024.3.7.1-aarch64.dmg) | 950743474 | [SHA-256](https://download.jetbrains.com/idea/ideaIC-2024.3.7.1-aarch64.dmg.sha256) |
| Intel / x86_64 | [ideaIC-2024.3.7.1.dmg](https://download.jetbrains.com/idea/ideaIC-2024.3.7.1.dmg) | 960390082 | [SHA-256](https://download.jetbrains.com/idea/ideaIC-2024.3.7.1.dmg.sha256) |

2026-10-06 实际读取的官方 SHA-256：

```text
9ea06122b3917fe1f252e28cd0448fed47e5c723917e1cd3188356a728b16461  ideaIC-2024.3.7.1-aarch64.dmg
3decf9108691293922f87b3596154a6b7738edff0c2170ecc4cb39737117153a  ideaIC-2024.3.7.1.dmg
```

两条 DMG 链接均经 HEAD 跟随到 `download-cdn.jetbrains.com` 并返回 HTTP 200，长度与发行 API 一致。它们是两个独立架构的完整安装包，总计约 1.91 GB；不要仅准备其中一个供所有 Mac 使用。研究阶段未下载 DMG。当前核验未覆盖 2024.3.7.1 对每种 macOS 版本的实际运行兼容性，旧系统应先在团队样机试装。

Community Edition 的核心按 Apache 2.0 提供，部分随附插件有独立免费条款；保留官方原包及其中的许可证。`IIC` 发行 API 含 `licenseRequired: true` 字段，不能仅凭该字段把社区版判为收费产品。[JetBrains Community Edition 条款](https://www.jetbrains.com/legal/docs/toolbox/user_community/)、[官方商业开发使用说明](https://sales.jetbrains.com/hc/en-gb/articles/360021922640-Can-I-use-free-versions-of-IntelliJ-IDEA-and-PyCharm-for-developing-commercial-proprietary-software)

## 已确认适配的免费插件

下列版本来自官方 Marketplace stable 更新 API；同时以 JetBrains 公开下载接口传入 `build=IC-243.28141.41` 发起 HEAD 请求，服务端选择的 `updateId` 与下表一致，最终均返回 HTTP 200。`since` / `until` 表示声明的兼容范围；没有上限不等于所有功能已通过实机测试。[官方按 build 下载说明](https://plugins.jetbrains.com/docs/marketplace/plugin-update-download.html)、[build 范围说明](https://plugins.jetbrains.com/docs/intellij/build-number-ranges.html)

| 插件 | 固定版本 / updateId | Marketplace 兼容 build | 字节数 | 官方离线 ZIP |
| --- | --- | --- | ---: | --- |
| Database Navigator | `4.1.0.3` / `1177352` | `231.9423.9 — 263.*` | 83426592 | [DBN-4.1.0.3.zip](https://plugins.jetbrains.com/files/1800/1177352/DBN-4.1.0.3.zip) |
| MyBatisX | `1.7.6` / `1049967` | `232.0 — 262.*` | 3294483 | [MybatisX-1.7.6.zip](https://plugins.jetbrains.com/files/10119/1049967/MybatisX-1.7.6.zip) |
| GenerateAllSetter | `2.8.5` / `1062692` | `213.0+` | 192249 | [GenerateAllSetter-2.8.5.zip](https://plugins.jetbrains.com/files/9360/1062692/GenerateAllSetter-2.8.5.zip) |
| Spring Boot Assistant（可选替代插件） | `601.0.7+242` / `1118264` | `242.0+` | 7534079 | [spring-boot-assistant-601.0.7_242.zip](https://plugins.jetbrains.com/files/17747/1118264/spring-boot-assistant-601.0.7_242.zip) |

插件 ZIP 无需按 Mac CPU 架构重复存储。上述下载地址会重定向至 JetBrains 官方 `downloads.marketplace.jetbrains.com` CDN。静态兼容性及文件信息可复查：

- Database Navigator：[详情与费用元数据](https://plugins.jetbrains.com/api/plugins/1800)、[指定更新](https://plugins.jetbrains.com/api/updates/1177352)、[版本页](https://plugins.jetbrains.com/plugin/1800-database-navigator/versions/stable/1177352)。XML ID 为 `DBN`；`pricingModel=FREE`，许可链接为 Apache 2.0；源码：[Oracle 官方仓库](https://github.com/oracle/database-navigator)。该版本声明了按需下载 JDBC 驱动的功能，离线数据库连接不能只凭插件 ZIP 判定准备完成；还应验证所用 MySQL 驱动已随包提供或另行缓存。
- MyBatisX：[详情与费用元数据](https://plugins.jetbrains.com/api/plugins/10119)、[指定更新](https://plugins.jetbrains.com/api/updates/1049967)、[全部版本](https://plugins.jetbrains.com/api/plugins/10119/updates?size=100)。XML ID 为 `com.baomidou.plugin.idea.mybatisx`；`pricingModel=FREE`，Marketplace 许可链接为 MIT，源码为作者提供的 [MybatisX 仓库](https://gitee.com/baomidou/MybatisX/)。**不要下载当前最新版 `1.7.7`：其最低 build 为 `251.0`，不支持 IDEA 2024。** 已读取 `1.7.6` ZIP 中的 `plugin.xml`，其中范围为 `232 — 263.*`，比 Marketplace API 的上限宽；目标 `243.28141.41` 同时落在两者范围内。必需依赖为 `com.intellij.java`，数据库、Spring、Spring Boot、Kotlin、IntelliLang 均标记为可选。
- GenerateAllSetter：[详情与费用元数据](https://plugins.jetbrains.com/api/plugins/9360)、[指定更新](https://plugins.jetbrains.com/api/updates/1062692)。XML ID 为 `com.bruce.intellijplugin.generatesetter`；`pricingModel=FREE`；作者的 [license 文件](https://github.com/gejun123456/intellij-generateAllSetMethod/blob/master/license) 为 GNU GPL Version 2 文本。已读取 `2.8.5` ZIP 中的 `plugin.xml`：必需 `com.intellij.modules.java`，Kotlin、Groovy 为可选。离线分发保留许可证，并为对应源码提供随包副本或符合该许可要求的获取方式；本次尚未核验哪个源码 tag 精确对应 Marketplace 二进制。
- Spring Boot Assistant：[详情与费用元数据](https://plugins.jetbrains.com/api/plugins/17747)、[指定更新](https://plugins.jetbrains.com/api/updates/1118264)。XML ID 为 `dev.flikas.idea.spring.boot.assistant.plugin`；`pricingModel=FREE`，MPL 2.0。作者明确面向 Community Edition，提供 Spring Boot YAML / properties 配置辅助，且与原 Spring Assistant 是不同插件。[作者说明与源码](https://github.com/flikas/idea-spring-boot-assistant)。已读取 ZIP 中的 `plugin.xml`：必需 `com.intellij.modules.platform`、`com.intellij.modules.java`、`com.intellij.modules.lang`、`org.jetbrains.plugins.yaml`、`com.intellij.properties`。本次未确认目标 DMG 中 YAML / Properties 的随附与启用状态，内网使用前须检查；若缺失，要再准备匹配 `243.28141.41` 的依赖插件。

## 不纳入默认免费包的候选

| 候选 | 核验结果 | 处理 |
| --- | --- | --- |
| Spring Boot Helper（Marketplace ID `18622`） | `2023.3.6` / updateId `1104365`，最低 build `233.0`，无上限；适配范围包含目标，但 `pricingModel=PAID` | 不作为免费插件默认分发；需要时使用者按作者条款取得许可 |
| 原 Spring Assistant（Marketplace ID `10229`） | 最新 `0.12.0` / updateId `44968`，build `172.0 — 201`，Marketplace 支持列表只到 IDEA 2019.3.5；免费 / MIT | 不适配 `243`，不打包、不通过修改 plugin.xml 强装 |

Spring Boot Helper 的元数据：[插件详情](https://plugins.jetbrains.com/api/plugins/18622)、[指定版本](https://plugins.jetbrains.com/api/updates/1104365)、[作者许可](https://github.com/eltonsandre/intellij-spring-boot-helper/blob/main/LICENSE_PLUGIN.md)。其官方原包为 [spring-boot-helper-2023.3.6.zip](https://plugins.jetbrains.com/files/18622/1104365/spring-boot-helper-2023.3.6.zip)，4910227 字节；能下载 ZIP 不代表免费使用。本次没有下载或安装它。

原 Spring Assistant 的元数据：[插件详情](https://plugins.jetbrains.com/api/plugins/10229)、[指定版本](https://plugins.jetbrains.com/api/updates/44968)。旧包追溯链接为 [intellij-spring-assistant-0.12.0.zip](https://plugins.jetbrains.com/files/10229/44968/intellij-spring-assistant-0.12.0.zip)，1027198 字节；仅用于记录，不作为 IDEA 2024 下载清单。

## 校验与验证边界

本次查看的 Marketplace 元数据和下载响应头未提供官方 SHA-256，响应头的 ETag 不能作为 SHA-256 使用。维护者实际下载后应计算本地 SHA-256，写入发放目录的校验清单。研究时为读取描述文件下载了三个小 ZIP，得到以下**本地计算值（不是官方独立公布值）**：

```text
7ce651b368306a0bf037f55cc2a4eb1c7c0faf56ac6da35665a4448b2c859db0  MybatisX-1.7.6.zip
66af4972ec650e7165c73186c12f3992f5267aa2c8a697fa12c1997a113ca7d3  GenerateAllSetter-2.8.5.zip
391f77c7d08e97cca736bd2126e36f6d9a42e1c8a8b991d1a7424c4015f29d77  spring-boot-assistant-601.0.7_242.zip
```

待离线包形成后，在目标 IDEA 内通过 `Settings → Plugins → 齿轮 → Install Plugin from Disk` 选择原始 ZIP，按 IDE 提示重启，再验证数据库连接、Mapper/XML 跳转、setter 生成和配置提示。研究阶段未执行安装或功能验收；Database Navigator 包内容、额外 JDBC 驱动、macOS 系统版本以及 Spring 替代插件的目标 IDE 随附依赖仍需在发放前确认。[Oracle 官方从磁盘安装说明](https://docs.oracle.com/en/database/oracle/database-navigator/3.7/dbnug/oracle-database-navigator-users-guide.pdf)
