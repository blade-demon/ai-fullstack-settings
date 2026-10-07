# 修复历史与结果 review

每次修复的结果默认保存到 `~/Library/Logs/team-java-env/history/`，每次操作单独建目录。成员可打开操作结果中显示的目录查看记录；维护者也可运行 `bash dev-kit/.support/scripts/history.sh` 查看历史，或用 `REPAIR_HISTORY_DIR` 指定其他绝对路径。

| 文件 | 用途 |
| --- | --- |
| `report.md` | 本次范围、项目、最终结果、阶段结果和配置修改清单 |
| `result.tsv` | 最终状态及退出码，可用于自动检查 |
| `steps.tsv`、`logs/` | 安装、复用、IDEA 项目预检、验证和终端构建的逐步结果 |
| `before-scan.txt`、`after-scan.txt` | 修复前后扫描结果 |
| `config-changes.diff` | 工具管理区块的差异，采用零行上下文；其他个人配置只留在私有备份 |
| `before/`、`after/` | 环境文件和终端配置的前后备份 |
| `before-files.tsv`、`after-files.tsv` | 配置路径、类型和 SHA-256 摘要 |
| `plugins-result.tsv` | 六个插件的安装、复用、升级及备份路径 |
| `plugins-verification.tsv` | 最终插件验证结果，保留此前安装记录 |
| `plugin-backups/` | 被替换的已知旧版本插件备份（有升级时生成） |

| 最终状态 | 含义 |
| --- | --- |
| `SUCCEEDED` | 所选修复、SDK 与指定项目终端构建通过，IDEA 静态配置可解析；仍需启动 IDEA 并同步 |
| `PROJECT_BUILD_VERIFIED_IDEA_PENDING` | SDK 与终端构建通过，IDEA 项目待配置；总体退出码 `0`，仍需按报告完成 IDEA 设置 |
| `ENVIRONMENT_VERIFIED_NO_PROJECT` | 完整环境验证通过，未选择项目、未构建 |
| `COMPONENT_VERIFIED` | 所选单独组件验证通过，不代表业务项目构建成功 |

IDEA 项目预检只读读取项目 XML 和 SDK 登记表；待配置阶段以退出码 `2` 记录，继续进行 SDK 与终端构建验证。静态配置可解析不是 GUI 同步成功，报告不宣称 GUI 已可用。安装、SDK 验证、构建或历史保存失败时，脚本仍以非零状态退出并报告失败。

有项目的 SDK / IDEA 修复还会在预检前执行 SDK 名称同步，记录 `jdk.table.xml`、项目 SDK、Gradle JVM 和模块引用的前后快照。可分享差异仅显示相关 SDK 字段，原始文件仍在本机私有快照中；名称冲突或配置不安全会记录失败并阻止后续构建。

终端构建使用受管 JDK 8，按 IDEA 的 Wrapper 或 LOCAL 实际目录验证所选 Gradle 版本（默认 4.5.1，可用 `--gradle-version 6.8` 指定 6.8）；无 IDEA 项目配置时使用受管独立 Gradle 并提示待导入，未知配置会失败。默认执行 `build`，不跳过测试；仅安装完成或版本输出正常均不足以通过，脚本同时检查构建退出码和 `BUILD SUCCESSFUL`。

review 时先查看 `report.md`，再核对 `config-changes.diff` 和失败阶段日志。原始配置备份可能包含个人设置，仅供本机查看；分享排障信息时选择必要内容。历史目录使用私有权限，脚本不会自动上传记录，也不会自动回滚开发者后续修改。
