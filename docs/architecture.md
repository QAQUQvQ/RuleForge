# RuleForge M1 / M1+ 架构
本次用户请求是实施边界；原计划是产品参考，不将其中投稿或后续阶段当作本次授权。先给出设计后实现。
## 模块和目录
```text
backend/ruleforge/
  ingestion/     官方 CLI 适配、证据、规范化
  rules/         AST、Schema、纯求值器、验证发布服务
  domain/        角色、物品、战斗、命令、事件模型
  persistence/   SQLite v1 基线、v2 迁移和事务上下文
  api.py         FastAPI，只开放已实现接口
  cli.py         初始化、解析、清单登记、验证发布
backend/tests/   单测和真实证据/API 集成
frontend/src/   React/TypeScript 最小证据与 AC 页面
data/sources/   官方原始 PDF
data/runs/      每次解析的 raw/stdout/stderr/manifest
data/normalized/ 派生 DSL、证据和验证记录
docs/schemas/   Pydantic 导出 JSON Schema
scripts/       任务上下文准备及 Schema 导出
```
## 流程
官方 PDF -> xparse-cli --api free -> 原始 JSON/日志 -> 完整覆盖检查 -> 类型化来源和受限模板 -> 数值验证 -> SQLite 发布 -> AC API。
当前已验证皮甲 AC，引用 PDF 63/64/76。无甲草案未发布；来源与范围优先于预设示例。
## 数据库
实际 SQL：backend/ruleforge/persistence/schema.sql。
documents 保留 URL、PDF SHA-256、license 和路径；parse_runs 保留原始 manifest；source_spans 保存 JSON pointer、物理/印刷页、原文和哈希。
rules 以 (id,version) 为主键；rule_sources 多对多关联来源；verifications 将通过记录绑定到 DSL 和 manifest 哈希。
characters/encounters/commands/events 为未来阶段预留；当前没有战斗状态写入接口。
SQLite foreign_keys=ON，异常事务回滚。迁移以 user_version 标识，当前 v2；v1 基线保持不变，升级使用显式 migration_v2.sql。
## 来源边界
保留 CLI 原始 JSON，不重排或修改。页码来自实际 page_number 且核对 pages[].element_ids；印刷页只采集唯一数字 Footer，无法确定则 null。
全页覆盖同时核对 get_doc_info、metadata.page_count、success_count、Success 页面集合。
执行时重新核对 PDF、JSON、日志、清单、数据库引用与 DSL。哈希用于发现本地意外篡改，不是第三方签名或恶意系统管理员防护。
section 是规范化标签；坐标保留原始数列，不假设四点矩形。
完整 PDF 解析不代表全文规则编译完成。
## 安全执行
Pydantic extra=forbid、严格字段类型；JSON AST 白名单；深度<=8，节点<=64，整数上下限。
无 eval/exec、shell 表达式、任意导入、动态属性、循环或用户函数。API 不接收 DSL 代码；仅运行已验证版本。
皮甲 + 无盾 + 无替代公式之外的情况明确拒绝。本阶段算基础装备 AC，不结算掩护、法术等战斗修正。
原文只作为数据；不执行原文中的指令或 HTML。
## xParse
使用 intsig-textin/xparse-skills 的已检查技能，CLI 2.5.0；技能文档本地快照。
不自行实现认证、配额、PDF 拆分/合并或 OCR。固定免费端点，没有 paid 分支，没有自动重试。
结构化 xparse_error.v1 即使进程 exit=0 也判定失败。等待授权/资金或不可重试错误必须停止服务调用。
PDF/JSON、CLI 原始错误与本地验证错误分开保存，不能将本地失败说成 TextIn 服务失败。
## 后续状态与事件设计
角色：六维、装备、HP/临时 HP、速度、资源、状态及版本。
战斗：先攻队列、当前角色、阶段、轮次、行动/附赠/反应/移动、位置、持续效果。
reaction 阶段必须有 ReactionWindow，处理后回到 resume_phase，不能简单排到普通回合末。
命令：类型判别联合、command_id、actor_id、expected_version，载荷固定字段。
事件：sequence、command_id、前后状态哈希、版本化规则引用、来源、骰值、轨迹。
M2/M3 必须实现同一事务提交状态+命令+事件、幂等和乐观版本控制。本次只有 Schema 与约束，没有宣称此状态机已实现。

## M1+ 增量架构

新增 `catalog/equipment.py`、`catalog/models.py` 和 `catalog/service.py`，分别负责装备定义、五类记录与生命周期。当前 `domain.Equipment` 继续表示角色装备状态；`EquipmentDefinition` 表示可版本化规则目录。`catalog.models.RuleRecord` 为通用记录基类；`rules.models.RuleRecord`/`LeatherRuleRecord` 保留原三来源执行封装，`NormalizedRuleRecord` 指向通用模型，避免破坏旧导入。

`rules/sources.py` 的 `SourceReference` 支持通用 role、文档 SHA、解析任务 ID、element ID、JSON Pointer、xParse 章节关系、物理页/印刷页、表格坐标、原文/哈希、坐标和审核状态。`verify_reference` 复用原 `verify_span` 和 `checked_file`，额外校验任务/文档、元素归属、页码成员关系、Footer、章节、坐标、表格位置。未知页码使用 null；原文逐字比对，禁止改写证据。

离线管线：既有 manifest/JSON → Extractor Registry → typed candidate + sources → create_candidate → validate_candidate → 待审核目录。抽取器是受控 Python 代码，不生成或动态执行代码。每次调用产生独立 normalization_id；extraction_run_id 引用现有解析任务，record_version 是记录版本，schema_version 是模型格式版本，ruleset 是规则集版本。

审核与能力独立：validation_status = extracted/validated/review_required/rejected；review_status = review_required/approved/rejected；execution_status = executable/partially_executable/reference_only/unsupported。Schema 校验只能检查结构，来源校验只能证明证据一致；人工审核负责语义。新目录尚无运行适配器，所以服务拒绝任何 executable/partially_executable 的新候选或发布请求。旧皮甲执行仍通过 rules.service 的全部专用门禁。

v2 保留 schema.sql 的 v1 基线，由 db.initialize 按 user_version 在一个 BEGIN IMMEDIATE 事务内执行显式 migration_v2.sql。新增 source_references（FK parse_runs）、normalized_records（PK id+record_version）、record_sources（记录与来源多对多）、review_decisions（版本化审核历史）。装备 payload 直接存储在 normalized_records 的强类型 JSON，避免重复设备表；ruleset 目前只有 srd-5.1，暂不建立无实际元数据的 rulesets 表。迁移无 DROP/重建，失败全部回滚。

验证报告和审核决定绑定记录内容 + 所有来源 + manifest 哈希；发布和 published_only 读取都重新验源。对已发布记录复验失败会撤销发布并回到待审核。普通 get_record/list_records 可查看候选，因此消费端必须显式使用 published_only=True；这仍仅代表可检索目录。源文件哈希不是外部数字签名，防护范围沿用 M1 的本地意外篡改边界。

抽取失败保留类别、错误类型和原因；历史报告不可被后续成功结果覆盖。表格 HTML 仅用标准库解析为数据，不渲染、不执行。Barbarian 特殊跨表续接保留两个来源位置；其他不明确续接按失败处理。
