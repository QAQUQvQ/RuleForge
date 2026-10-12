# RuleForge M1 架构
本次用户请求是实施边界；原计划是产品参考，不将其中投稿或后续阶段当作本次授权。先给出设计后实现。
## 模块和目录
```text
backend/ruleforge/
  ingestion/     官方 CLI 适配、证据、规范化
  rules/         AST、Schema、纯求值器、验证发布服务
  domain/        角色、物品、战斗、命令、事件模型
  persistence/   SQLite schema v1 和事务上下文
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
SQLite foreign_keys=ON，异常事务回滚。迁移以 user_version 标识，目前仅 v1；新版本必须新增显式迁移。
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
