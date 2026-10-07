# IDEA 2025 与离线插件来源核验

核验日期：**2026-10-07**。当前基线为 **IntelliJ IDEA Community Open Source 2025.3.6.1**，面向 macOS Apple Silicon / Intel。2024 已从有效下载清单和新安装基线移除；本文替代此前针对 2024.3.7.1 与 Lombok 243 系列的下载建议。旧验收记录只代表当时版本，不作为新版本已完成安装或 GUI 验收的依据。

## 发行版本与应用标识

JetBrains 从 2025.3 起在官网提供统一发行版，同时在 `JetBrains/intellij-community` 发布仅包含开源部分的构建。本工具固定使用后者的 CE / OSS 原包。官方 GitHub Release 列表中，2025 系列最高稳定版本为 **2025.3.6.1**，发布日期为 **2026-07-29**；2025.2.6.3 属于较早的版本分支，不作为此次基线。来源：[JetBrains 发行方式说明](https://blog.jetbrains.com/idea/2025/07/intellij-idea-unified-distribution-plan/)、[官方社区版下载说明](https://youtrack.jetbrains.com/projects/DS/articles/SUPPORT-A-2314/IntelliJ-IDEA-Community-Edition)、[GitHub Release 列表 API](https://api.github.com/repos/JetBrains/intellij-community/releases?per_page=100)、[2025.3.6.1 Release](https://github.com/JetBrains/intellij-community/releases/tag/idea%2F2025.3.6.1)。

该版本 tag 的官方构建源码明确了以下标识：

| 项目 | 当前值 |
| --- | --- |
| 应用目录名 | `IntelliJ IDEA CE.app` |
| macOS bundle ID | `com.jetbrains.intellij.ce` |
| DataDirectorySelector | `IdeaIC2025.3` |
| 产品代码 | `IC` |
| 两架构 DMG 实测 build | `IC-253.33813.55` |
| 默认配置目录 | `~/Library/Application Support/JetBrains/IdeaIC2025.3` |
| 默认用户插件目录 | `~/Library/Application Support/JetBrains/IdeaIC2025.3/plugins` |

应用名称、bundle ID 和目录标识依据该 tag 的 [IdeaCommunityProperties.kt](https://github.com/JetBrains/intellij-community/blob/idea/2025.3.6.1/build/src/org/jetbrains/intellij/build/IdeaCommunityProperties.kt)；版本和 `IC` 产品代码依据 [IdeaApplicationInfo.xml](https://github.com/JetBrains/intellij-community/blob/idea/2025.3.6.1/community-resources/resources/idea/IdeaApplicationInfo.xml)。2026-10-07 已下载两份 CE 原包并核对官方摘要，然后分别只读挂载：`Contents/Info.plist` 的版本均为 `2025.3.6.1`、构建号均为 `IC-253.33813.55`、bundle ID 均为 `com.jetbrains.intellij.ce`；`Contents/Resources/product-info.json` 的产品代码为 `IC`、目录标识为 `IdeaIC2025.3`。检查后已卸载挂载，未启动或安装 IDEA。

## 两架构官方 DMG

下列下载地址、字节数和 SHA-256 均来自 [JetBrains 官方 GitHub Release 资产 API](https://api.github.com/repos/JetBrains/intellij-community/releases/tags/idea%2F2025.3.6.1)。摘要读取资产的 `digest` 字段，已去掉其 `sha256:` 前缀写入下载清单；不是沿用旧版的校验文件，也不是统一发行版的 DMG 摘要。

| 平台 | 官方原包 | 字节数 |
| --- | --- | ---: |
| Apple Silicon / arm64 | [idea-2025.3.6.1-aarch64.dmg](https://github.com/JetBrains/intellij-community/releases/download/idea/2025.3.6.1/idea-2025.3.6.1-aarch64.dmg) | 792071294 |
| Intel / x86_64 | [idea-2025.3.6.1.dmg](https://github.com/JetBrains/intellij-community/releases/download/idea/2025.3.6.1/idea-2025.3.6.1.dmg) | 802415690 |

官方 SHA-256：

```text
95d0a589966484688dfdd14d5396edca38d8aa3462c366e286e1422b40afafbd  idea-2025.3.6.1-aarch64.dmg
a4655cbf9b4c7d97efceff3e10221777124a445d9a5ad02b420002fd0ddfe4ce  idea-2025.3.6.1.dmg
```

两个 DMG 合计 1594486984 字节，约 1.59 GB；应按目标电脑架构提供对应文件。本轮已完成实际文件摘要校验和只读包内元数据检查；后续分发仍须重新校验文件。资源校验通过不等于已在每种 macOS 或两种 CPU 的真实电脑上运行通过。

## 六个固定插件与兼容性

本轮复核了 JetBrains Marketplace 原始更新 API，以及现有 ZIP 内 JAR 的 `META-INF/plugin.xml`；新 Lombok 也已下载官方原包并读取描述文件。目标为 `IC-253.33813.55`。旧 Lombok `243.28141.18` 的上限是 `243.*`，必须替换；另外五个现有插件均覆盖 253，保留原固定版本。

| 插件 | 固定版本 / updateId | Marketplace 范围 | 实际 plugin.xml 范围 | 字节数 |
| --- | --- | --- | --- | ---: |
| Database Navigator | `4.1.0.3` / `1177352` | `231.9423.9 — 263.*` | `231.9423.9 — 263.*` | 83426592 |
| MyBatisX | `1.7.6` / `1049967` | `232.0 — 262.*` | `232 — 263.*` | 3294483 |
| GenerateAllSetter | `2.8.5` / `1062692` | `213.0+` | `213+` | 192249 |
| GsonFormatPlus | `1.6.1` / `115983` | `135.121+` | `135.121+` | 169687 |
| Key Promoter X | `2026.1.2` / `1098878` | `241.0+` | `241+` | 66926 |
| Lombok | `253.28294.251` / `902657` | `253.28294 — 253.*` | `253.28294 — 253.*` | 530229 |

`+` 表示描述文件没有声明最高 build，不代表所有后续 IDE 版本的功能均已实机验证。MyBatisX 的元数据与实际包上限不同，但 253 同时位于两者范围内。

官方固定下载和元数据：

| 插件 | 官方原包 | 官方更新元数据 |
| --- | --- | --- |
| Database Navigator | [DBN-4.1.0.3.zip](https://plugins.jetbrains.com/files/1800/1177352/DBN-4.1.0.3.zip) | [update 1177352](https://plugins.jetbrains.com/api/updates/1177352) |
| MyBatisX | [MybatisX-1.7.6.zip](https://plugins.jetbrains.com/files/10119/1049967/MybatisX-1.7.6.zip) | [update 1049967](https://plugins.jetbrains.com/api/updates/1049967) |
| GenerateAllSetter | [GenerateAllSetter-2.8.5.zip](https://plugins.jetbrains.com/files/9360/1062692/GenerateAllSetter-2.8.5.zip) | [update 1062692](https://plugins.jetbrains.com/api/updates/1062692) |
| GsonFormatPlus | [GsonFormatPlus.zip](https://plugins.jetbrains.com/files/14949/115983/GsonFormatPlus.zip) | [update 115983](https://plugins.jetbrains.com/api/updates/115983) |
| Key Promoter X | [Key_Promoter_X-2026.1.2.zip](https://plugins.jetbrains.com/files/9792/1098878/Key_Promoter_X-2026.1.2.zip) | [update 1098878](https://plugins.jetbrains.com/api/updates/1098878) |
| Lombok | [lombok-253.28294.251.zip](https://plugins.jetbrains.com/files/6317/902657/lombok-253.28294.251.zip) | [update 902657](https://plugins.jetbrains.com/api/updates/902657) |

GsonFormatPlus 的本地文件命名为 `GsonFormatPlus-1.6.1.zip`，内容保持原样。六个 ZIP 不需要按 Mac CPU 架构重复保存。

同时调用官方 `plugins/list?pluginId=…&build=IC-253.33813.55` 查询完整 CE 构建的兼容版本，返回 Database Navigator 4.1.0.3、GenerateAllSetter 2.8.5、GsonFormatPlus 1.6.1、Key Promoter X 2026.1.2、Lombok 253.28294.251，MyBatisX 则返回 1.7.7。复查入口：[DBN](https://plugins.jetbrains.com/plugins/list?pluginId=1800&build=IC-253.33813.55)、[MyBatisX](https://plugins.jetbrains.com/plugins/list?pluginId=10119&build=IC-253.33813.55)、[GenerateAllSetter](https://plugins.jetbrains.com/plugins/list?pluginId=9360&build=IC-253.33813.55)、[GsonFormatPlus](https://plugins.jetbrains.com/plugins/list?pluginId=14949&build=IC-253.33813.55)、[Key Promoter X](https://plugins.jetbrains.com/plugins/list?pluginId=9792&build=IC-253.33813.55)、[Lombok](https://plugins.jetbrains.com/plugins/list?pluginId=6317&build=IC-253.33813.55)。接口用法见[官方详情 API](https://plugins.jetbrains.com/docs/marketplace/plugin-details.html)和[按 build 下载 API](https://plugins.jetbrains.com/docs/marketplace/plugin-update-download.html)。

**MyBatisX 1.7.7 可以适配当前基线。** 其最低 build 为 `251.0`、最高为 `263.*`，见[官方更新元数据](https://plugins.jetbrains.com/api/updates/1171092)。此前“不使用 1.7.7，因为 IDEA 2024 不支持”的建议已失效；本次保留 1.7.6，是因为它仍兼容，不需要随着 IDEA 升级更换。其他研究候选不纳入本次六插件清单。

## 必需依赖与离线边界

以下来自实际 `plugin.xml`，未通过修改描述文件放宽兼容范围：

| 插件 | XML ID | 必需依赖 |
| --- | --- | --- |
| Database Navigator | `DBN` | `com.intellij.modules.platform`、`com.intellij.modules.lang` |
| MyBatisX | `com.baomidou.plugin.idea.mybatisx` | `com.intellij.java` |
| GenerateAllSetter | `com.bruce.intellijplugin.generatesetter` | `com.intellij.modules.java` |
| GsonFormatPlus | `GsonFormatPlus`（沿用插件名称） | `com.intellij.modules.java` |
| Key Promoter X | `Key Promoter X`（沿用插件名称） | `com.intellij.modules.lang` |
| Lombok | `Lombook Plugin`（历史拼写） | `com.intellij.modules.lang`、`com.intellij.modules.platform`、`com.intellij.modules.java` |

Database Navigator 的 Java、JSON、Maven、调试器等扩展依赖均为可选；MyBatisX 的数据库、Spring、Spring Boot、Kotlin、IntelliLang 依赖也均为可选。GenerateAllSetter 的 Kotlin 和 Groovy 支持为可选。这些可选功能不能据此视为已经在开源版中启用。

数据库连接可能仍需额外 JDBC 驱动和网络访问；插件 ZIP 不包含全部业务依赖缓存。IDEA 的 Lombok 插件与项目中的 Lombok 依赖版本分别管理，使用步骤见[IDE 指南](../environment/ide.md#lombok-安装与启用步骤)。

## 插件本地摘要与验收边界

上述 Marketplace 更新元数据未提供独立 SHA-256，下载清单中的插件摘要字段仍为 `-`，下载流程生成同名 `.sha256` 本地记录。2026-10-07 对现有五个原始包和新下载 Lombok 计算得到以下值；**这是本地文件摘要，不是官方独立发布的摘要**：

```text
ca5420425544a5a87b3f95a06766ba9e57d04ed404f5b2e187cb7c24b75f77a9  DBN-4.1.0.3.zip
7ce651b368306a0bf037f55cc2a4eb1c7c0faf56ac6da35665a4448b2c859db0  MybatisX-1.7.6.zip
66af4972ec650e7165c73186c12f3992f5267aa2c8a697fa12c1997a113ca7d3  GenerateAllSetter-2.8.5.zip
36e98bbfbf6900704e87a8eea99635b076c49ae69ebca058e77f0fd3c0f6f250  GsonFormatPlus-1.6.1.zip
dd76969715fb8d1d2e1f1fee4e9961c8f9b0d49f835a2c7a7d0c1e71709fae4c  Key_Promoter_X-2026.1.2.zip
051776507843b46cc1764e733cee8b806df8139db81553420f2ff6751f4087a0  lombok-253.28294.251.zip
```

成员可使用菜单 `5` 安装全部固定插件，或从 IDEA 的 `Settings → Plugins → 齿轮 → Install Plugin from Disk` 选择原始 ZIP，无需预先解压。按提示重启后，仍须在真实项目中验证数据库连接、Mapper/XML 跳转、setter 和 JSON 代码生成、快捷键提示与 Lombok 识别。

本轮来源核验覆盖官方发行元数据、固定下载地址、摘要及插件声明范围；不宣称已启动真实 IDEA、完成插件功能验收或完成 Gradle GUI 同步。保留原始安装包及其中的许可证，实际安装结果和项目构建结果分别记录。

本轮还使用六个真实官方插件 ZIP，在临时 HOME 与微型 IDEA 2025.3 fixture 中执行安装和 `--verify-only`，两次均通过；没有修改当前用户的 IDEA 或启动 IDE。
