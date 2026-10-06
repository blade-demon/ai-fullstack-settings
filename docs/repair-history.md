# 修复历史与结果 review

成员在主菜单选择 `10`，可以查看每次修复的结果和记录位置。默认保存到 `~/Library/Logs/team-java-env/history/`，每次操作单独建目录；维护者可用 `REPAIR_HISTORY_DIR` 指定其他绝对路径。

| 文件 | 用途 |
| --- | --- |
| `report.md` | 本次范围、项目、最终结果、阶段结果和配置修改清单 |
| `result.tsv` | 最终状态及退出码，可用于自动检查 |
| `steps.tsv`、`logs/` | 安装、复用、验证和实际构建的逐步结果 |
| `before-scan.txt`、`after-scan.txt` | 修复前后扫描结果 |
| `config-changes.diff` | 工具管理区块的差异，采用零行上下文；其他个人配置只留在私有备份 |
| `before/`、`after/` | 环境文件和终端配置的前后备份 |
| `before-files.tsv`、`after-files.tsv` | 配置路径、类型和 SHA-256 摘要 |
| `plugins-result.tsv` | 五个插件的安装、复用、升级及备份路径 |
| `plugins-verification.tsv` | 最终插件验证结果，保留此前安装记录 |
| `plugin-backups/` | 被替换的已知旧版本插件备份（有升级时生成） |

`SUCCEEDED` 表示所选修复范围及指定项目的实际构建均通过。`ENVIRONMENT_VERIFIED_NO_PROJECT` 表示完整环境验证通过但未选择项目；`COMPONENT_VERIFIED` 表示单独组件验证通过。二者均不代表业务项目构建成功。任何安装、验证、构建或历史保存失败，脚本均以非零状态退出并报告失败。

项目构建使用配置好的 JDK 8 和 Gradle 4.5.1，默认执行 `build`，不跳过测试。仅安装完成、Gradle 版本输出正常或打印了成功文字均不足以通过；脚本同时检查构建退出码和 `BUILD SUCCESSFUL`。

review 时先查看 `report.md`，再核对 `config-changes.diff` 和失败阶段日志。原始配置备份可能包含个人设置，仅供本机查看；分享排障信息时选择必要内容。历史目录使用私有权限，脚本不会自动上传记录，也不会自动回滚开发者后续修改。
