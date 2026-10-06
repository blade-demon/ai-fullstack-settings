# IDEA JDK 8 名称统一实现计划

**目标：** 修复时使用 `IDEA_JDK_NAME`（默认 `azul-1.8`）统一实际 JDK 8 的 IDEA 登记和所选项目引用，避免同目录的不同名称再次出现。

**设计：** 增加独立 SDK 同步入口，复用现有 JDK 探测、IDEA XML 校验与路径解析。使用 macOS 自带 `xmllint`、`xsltproc` 编辑 XML，不增加成员端 Python 依赖。统一修复入口在 SDK 就绪后、项目预检和构建前调用同步，审计记录相关配置前后快照。

**范围：** 当前工具仓库代码、临时目录中的测试和操作说明。此开发任务不修改本机 IDEA 或业务项目配置。

## 配置与保护约束

- 保留实际 JDK 安装目录；名称由非空 `IDEA_JDK_NAME` 覆盖。
- Project SDK、当前关联项目 Gradle JVM 使用统一名称；所选项目模块中指向被合并名称的显式 SDK 引用同步更新。
- 同目录的 SDK 名称合并为一个；其他 JDK、Gradle 分发和其他项目关联设置保留。
- 尚未导入项目继续以退出码 `2` 报告待配置；扫描入口保持只读。
- IDEA 运行中、同名 SDK 指向其他目录、符号链接、不安全或无法可靠解析的 XML，在改写前失败。
- 所有变更先准备和校验；首次修改备份 `.bak`；重复执行不更改相同配置及备份。
- `--dry-run` 不写文件、创建备份、联网或执行 SDK。
- 仅迁移所选项目；其他项目若仍引用已合并的旧名称，也需通过同一入口迁移。

## 执行顺序

- [x] 核对现有修复、审计、分发与 XML 预检接口；运行环境验证基线。
- [x] 新增 `tests/test_idea_sdk_sync.py`，用同目录双名称及旧项目引用的 XML 复现问题，确认测试失败。
- [x] 实现 `config-idea-sdk.sh` 与 XML 转换资源，验证去重、引用迁移、新登记、幂等和异常保护。
- [x] 先新增修复调度/审计测试，确认缺少同步步骤和配置快照时失败，再接入 `repair-env.sh`、`audit.sh` 与配置默认值。
- [x] 更新分发白名单、README、运行环境与 IDE 指南、成员说明；保证分发包含新入口及其资源。
- [x] 运行相关测试与完整 unittest 集合，检查 Bash 语法、差异格式，并由独立代理审查边界和回归风险。

## 验证命令

```bash
python3 -m unittest discover -s tests -p 'test_idea_sdk_sync.py' -v
python3 -m unittest discover -s tests -p 'test_repair.py' -v
python3 -m unittest discover -s tests -p 'test_distribution.py' -v
python3 -m unittest discover -s tests
git diff --check
```

## 进展

- 环境验证基线：17 项通过。
- 核心 XML 同步与测试已交给独立代理；修复接入、审计和文档分别处理，避免并行改写同一文件。
- 独立审查发现的边界已补回归：独立模块 SDK 保留、发布失败和信号中断恢复当次原件、模块扫描失败停止、预演不对未经验证的目录断言冲突。
- XML 统一安全入口只接受 UTF-8/ASCII 与规范 UTF-16，先解码检查 DTD/ENTITY 再解析，拒绝 UTF-7、IBM037、UTF-32 等编码；安全检查保持只读。
- 分发验证：18 项通过。核心同步、安全 XML、修复接入仍由最终完整测试和复核确认。
- SDK 独立复核的全部发现已修复；最终核心回归为 25 项，包含同名同物理目录的预演去重。
- 完整回归 373 项全部通过；分发服务将 `.xsl` 纳入文本换行规范化，跨平台打包回归通过。Bash 3.2、Python 3.8 语法与差异格式检查通过。
