# M3 implementation report

实现与场景验收：2026-10-15；最终全量回归反馈及前端构建：2026-10-19（Asia/Shanghai）。

## 基线与工作区

实施分支：`file-upload`。实施起始 HEAD：`39421442e6aec180a0d88e48f7bcc0166d0a4852`。
首次交付为未提交工作区改动；2026-10-19 用户随后明确授权将当前 M3 提交并推送至
现有 `file-upload` 分支。对应提交以 Git 历史为准。

原有未跟踪文件 `data/local-checks/m2-tests.xml`、`data/setup/account-status.json`、
`data/setup/skill-installation.json`、`docs/competition/` 均保留。
系统 Python 缺 FastAPI；实际使用项目 `.venv/Scripts/python.exe`。
修改生效前基线：**222 passed，0 failed，1 个 Starlette/httpx 弃用警告，439.20 秒**。

## 增量结构及所有权

继续使用 `CombatState`、`Combatant`、`Creature`、`ActionBudget`、`Effect`、
`ReactionWindow`、命令判别联合及 `DomainEvent`。原字段 `id`、`active_id`、
`effects` 分别承担 encounter_id、active_combatant、active_effects；位置和预算
保存在各 combatant 中，避免两套可写真相。

新增 `encounters/` 模块负责命令、纯状态转移、受控来源适配器与事件重放。
M2 `attack()`、`damage()`、`apply_hp()`、`Characters.ac_for()` 继续作为唯一计算内核。
M2 Runtime 仅抽出模板、适配器摘要和固定验证报告三个扩展点，原默认行为保留。
模型扩展会改变现有适配器摘要；已有许可失效时须显式重新验证，绝不自动重签。

创建遭遇时，服务器按人物 ID 与版本加载人物卡，验证装备和 AC，再复制快照。
客户端不能提交目标 HP/AC 覆盖服务端状态。遭遇中 HP 及临时 HP 与人物表独立；
本版本不提供回写人物卡操作。M4 如提供回写，须增加单独确认和人物版本 CAS。
PC/NPC/Monster 身份标签均可保存，但自动计算仅支持经过 M2 验证的一级 Fighter
人物快照，不表示支持任意怪物 stat block。

## 状态转换表

| 当前阶段 | 合法后继 | 触发及规则 |
|---|---|---|
| setup | turn_start / ended | DM 确认全部先攻；可取消遭遇 |
| turn_start | action / ended | 仅重置当前角色的行动、附赠上限、反应和有效速度 |
| action | turn_end / reaction / ended | 结束回合；已准备攻击的有效移动触发；DM 结束 |
| reaction | action / ended | 所有合资格者依次响应后恢复；DM 可结束 |
| turn_end | turn_start / ended | 轮转至下一角色；回到第一角色时 round+1 |
| ended | 无 | 除返回既有幂等收据外拒绝新命令 |

普通攻击、移动、Ready 等保持 action 阶段。开始命令产生两个事件；结束回合
产生三个事件。因此 `version` 按事件递增，等于 `event_sequence`，而非每命令加一。
所有这些事件在同一事务提交，读者不会看见半个回合切换。
先攻降序；同值可以显式指定顺序，或由 DM 确认采用稳定 ID 顺序。
HP=0 标记 `dm_required`，不擅自执行死亡豁免或怪物死亡策略；禁止普通行动和攻击，
但可结束回合或接受记录理由的 DM 裁定。

## 命令与原子事务

命令统一含 `command_id`、`encounter_id`、`actor_id`、`expected_version`、`payload`。
保留原 Attack/Move/Adjustment 顶层字段，payload 在服务层按命令类型严格验证。
新增 Start、Ready、SubmitReaction、DeclineReaction、EndEncounter。
无适配器的 Dash/Disengage/Dodge/法术/附赠动作不会伪装执行。

写入流程：`BEGIN IMMEDIATE` → 加载并核对快照 → 查已有命令收据 → 检查版本 →
验证完整历史 → 验证行动者/阶段/当前许可及绑定 → 调用 M2 → 生成固定事件 →
写 commands、events、CAS 更新 encounters → 来源文件最终 SHA 复核 → commit。
任意异常，包括提交前来源变化，均 rollback。

完全相同的重复命令必须先识别收据，才能容许原 expected_version 的正常重试；
这是一项对“先版本检查再幂等检查”的明确例外。同 ID 异内容返回
`command_id_conflict`；新 ID 的旧版本返回 `version_conflict`。
幂等返回历史收据，标记 `idempotent=true`，不再次扣资源，也不重新掷骰。

API 写端点需要 `X-RuleForge-Admin` 与配置的本地 DM token 恒定时间比较。
actor_id 是游戏行动者，不是登录身份。本版本是单 DM 本地服务，不是多租户多人授权系统。
DM Adjustment 和 EndEncounter 是审计记录的管理操作，可以在规则许可撤销后收尾；
其他新规则命令必须重新检查许可。

## 来源、反应、持续效果与地图边界

M3 使用既有 xParse JSON 与 PDF SHA 固定产物；不重新解析，不调用付费服务。
`encounters/templates.json` 固定两个 general_rule 模板：m3-turns、m3-ready。
来源索引及原文在 `encounters/evidence.py` 和模板中。反应恢复依据 element 2253；
Ready 依据 2341–2343；不将其中“每轮一次”的简述解释成全局轮次统一恢复。
候选可离线导入、验证，但正式人工审核、发布和 Runtime 注册必须分别执行。

唯一反应机制：消耗行动准备普通近战攻击；指定的另一个角色完成已确认普通移动，
最终位于准备者相邻 5 ft 时触发。DM 明确确认触发可感知。
按已确认先攻顺序响应；只接受窗口中的首个 pending actor 与相同 trigger_event_id。
提交才消耗 reaction，并使用 M2 攻击/伤害内核；放弃仅忽略本次触发，保留准备效果
及反应资源。最后一人响应后关闭窗口并恢复原行动者 action。
反应攻击没有无限递归触发，不支持借机攻击、Shield、Counterspell、准备法术或准备移动。

Ready 是有来源及许可的持续效果，到**准备者下一回合开始**到期。
通用边界计数器显式保存 duration_owner_id 与 turn_start/turn_end；不是每全局轮减一。
效果保存规则版本、applied_at、source_refs、active；已消费及过期效果不再参加计算。
遭遇结束将所有效果置为 inactive。相同 Ready 不能叠加。
Blinded 等 DM 备注只作记录；存在相关备注时自动攻击/移动拒绝，防止暗中忽略其影响。

地图是显式选择的项目演示约定：5 ft Chebyshev 方格距离，对角一步也是 5 ft。
不宣称这是 SRD 核心强制地图规则。仅允许进入 DM 确认的 clear_cells；路径必须逐格
相邻，逐步扣移动；拒绝未知格、占用格、超过有效速度、离开已建模敌人 5 ft 触及范围。
复杂地形、体型、挤压、飞行、额外触及范围等必须在创建/命令场景确认中排除，否则不应提交。

## 事件与确定性重放

固定保存事件 ID、命令、sequence、actor/targets、骰子、命中和暴击、伤害分量、
抗性/易伤/免疫、HP 前后、预算前后、全部来源引用、适配器摘要和规则版本。
事件 payload 包含服务端生成的状态字段补丁；重放只应用补丁，不调用计算器、RNG 或外部 API。
DM 的先攻排序、地图、场景确认、移动路径、HP 调整理由等外部决策也固定保存。

每个事件核对 before_hash、after_hash；事件自身摘要覆盖 payload、骰子、来源、元数据
及 previous_event_hash。事件链从 initial_hash 起始；最终与 snapshot 的 state_hash、
event_head 一致。还核对 SQL 索引列、完整命令收据、事件归属、连续序号及最终快照。
删除、重复、乱序、骰值或结果篡改、快照篡改都会拒绝。
历史重建不要求当前目录许可仍然有效；新命令仍须当前许可及原绑定一致。
摘要提供完整性检测，不是外部签名；攻击者若能一致重写整个数据库及所有摘要，
需靠独立备份/外部签名锚点检测，属于 M4 接口。

## SQLite v4

原 encounters/commands/events 表通过 ALTER TABLE 扩展，旧行原列保持。
新增 initial_json、initial_hash、state_hash、event_head；命令 request_hash/result_json；
事件 event_hash。新增 encounter_environment 隔离标记和命令遭遇索引。
保留所有外键及 encounter+sequence 唯一约束，连接启用 foreign_keys。
迁移与版本检查同一个 BEGIN IMMEDIATE；重复初始化幂等；失败 DDL 回滚；v5 以上拒绝降级。
旧遭遇没有真实事件初始数据时返回 legacy_encounter，不伪造历史。
`target_version=3` 仅供明确的历史迁移验证；已有 v4 不能用它降级。

正式库迁移前备份：`data/local-checks/m3-before-primary.sqlite3`。
迁移前正式库 v3、0 review_decisions、0 runtime_grants。
迁移后 v4；16 张旧表的原字段逐行比对完全一致，外键检查为空；原始 PDF/JSON SHA 不变。
实际逐表结果见 [`m3-data-audit.json`](m3-data-audit.json)。正式库审核和运行许可仍为 0。
测试全部在临时库模拟；三个演示位于 `data/local-checks/m3-demo-final.sqlite3`。
Demo 构造器要求显式参数、独立 m3-demo 文件名、持久化 demo 标记，并拒绝正式库路径/
同文件别名。默认应用不会从环境变量启用 demo；指向 demo 库也会得到 environment_mismatch。
正式执行另外拒绝 SIMULATED 审核人记录。

## 三个实际验收场景

完整逐命令输入和实际输出、事件摘要、源 ID、骰子及状态摘要见
[`m3-scenarios.json`](m3-scenarios.json)。保留独立 SQLite 可再查询完整来源及事件。

| 场景 | 实际结果 |
|---|---|
| A | 两名 Fighter，确定先攻，两次 `[15,1]` 攻击，目标 HP 12→8→4；完成两轮进入第 3 轮；16 个事件；重放一致 |
| B | Ready 消耗行动，Beta 移动触发窗口，Alpha `[15,2]` 反应使 HP 12→7；消耗反应，恢复原回合；再次 Ready 在 Alpha 下一回合开始到期；21 个事件；重放一致 |
| C | 三名参战者；after_command/after_event/after_snapshot 三故障点回滚；重复及并发重复只执行一次；版本竞争一成功一拒绝；历史骰值篡改返回 integrity_failure；恢复原历史后重放一致；9 个事件 |

三者均为**隔离模拟审核环境的实际运行**，不是已获正式授权的战斗演示。

## 验证记录

最终全量回归：**313 passed，1 warning，970.20 秒**。依据是用户于 2026-10-19
提供的本地 `.venv\Scripts\python.exe -m pytest -q` 完整终端结果，覆盖原有
M1/M1+/M2 的 222 项与 M3 新增的 91 项；该次运行未输出 JUnit 文件。
唯一警告为既有 `StarletteDeprecationWarning`（httpx TestClient 弃用），没有失败。

开发过程留存的实际执行证据：

| 执行 | 结果与出处 |
|---|---|
| 修改前全量基线 | 222 passed，439.20 秒 |
| 较早全量回归 | 309 passed，1 warning，950.00 秒；[JUnit](../data/local-checks/m3-full-suite.xml) |
| 增补反应恢复与零 HP 用例 | 2 passed，113.32 秒；[JUnit](../data/local-checks/m3-extra-tests.xml) |
| 最终纯状态机矩阵与身份/轮数保护 | 37 passed，0.72 秒；开发终端记录 |
| 最终代码 A/B/C 演示 | 三者全部 replay verified；[完整输入输出](m3-scenarios.json) |
| 用户最终全量运行 | 313 passed，1 warning，970.20 秒；2026-10-19 会话终端反馈 |

曾启动的最终 M3 单文件测试没有留下完整结果或 `m3-final-tests.xml`，不将其计为通过。
中间失败 XML 保留诊断历史；修复后的较早全量 309 项与用户最终全量 313 项记录分别列出。

2026-10-19 本地执行 `.\scripts\build-frontend.ps1`：**TypeScript 检查与 Vite 7.3.7
生产构建通过**，30 个模块，JS 246.73 kB、gzip 77.82 kB。另在当前 PowerShell
进程将 PATH 暂时限制为 Windows 系统目录，确认找不到 Node/pnpm 后再次构建通过；
使用本机既有 Codex Node 24.19.0 回退，结束后恢复进程 PATH。没有安装全局 pnpm。
脚本执行与 package.json 相同的 `tsc --noEmit` 和 `vite build`，任一步失败即停止。

实际浏览器验收使用显式隔离演示服务：创建遭遇并确认先攻；输入固定骰子 `[15,2]`
攻击，使目标 HP 12→7、攻击者行动消耗；结束回合切换 Beta；刷新恢复持久化状态；
进入占用格被拒且状态不变；查看事件及 PDF 来源；重放核验通过。
[验收截图](m3-ui-acceptance.jpg) 显示隔离模拟审核标记、HP、预算、当前行动者与重放结果。
正式库无模拟审批，审核和 Runtime 许可仍为 0；UI 验收不表示正式规则已经授权。

## M4 与限制

不实现完整职业、等级、法术、怪物能力、AI DM、路径搜索、多人实时同步和 Homebrew。
地图最多 400 clear_cells，创建最多 30 人；effects 保留历史标记，上限 200；超限原子拒绝。
zero HP/死亡/昏迷等仍交 DM 裁定；附赠动作只有预算，暂无受支持的消费命令。
固定骰子由本地 DM 显式输入，不是防作弊多人骰子系统。
每个新命令重放历史进行完整性核查，长遭遇性能可由 M4 的可信检查点优化。
M4 可扩展有权限的角色回写、身份隔离、更多规则适配器、外部事件签名、检查点与分页。

## 完整修改文件清单

以下为本次新增或修改；不包含原有未跟踪文件。

```text
README.md
backend/ruleforge/api.py
backend/ruleforge/combat/runtime.py
backend/ruleforge/domain/models.py
backend/ruleforge/encounters/__init__.py
backend/ruleforge/encounters/contracts.py
backend/ruleforge/encounters/demo.py
backend/ruleforge/encounters/evidence.py
backend/ruleforge/encounters/machine.py
backend/ruleforge/encounters/runtime.py
backend/ruleforge/encounters/service.py
backend/ruleforge/encounters/templates.json
backend/ruleforge/ingestion/evidence.py
backend/ruleforge/m3_api.py
backend/ruleforge/persistence/db.py
backend/ruleforge/persistence/migration_v4.sql
backend/tests/test_catalog.py
backend/tests/test_m2.py
backend/tests/test_m3.py
data/local-checks/m3-extra-tests.xml
data/local-checks/m3-full-suite.xml
data/local-checks/m3-regression.xml
data/local-checks/m3-tests.xml
docs/architecture.md
docs/m3-data-audit.json
docs/m3-implementation-report.md
docs/m3-scenarios.json
docs/m3-ui-acceptance.jpg
docs/rule-coverage.md
docs/schemas/combat-state.schema.json
docs/schemas/command.schema.json
docs/schemas/create-encounter.schema.json
docs/schemas/event.schema.json
docs/testing.md
frontend/index.html
frontend/src/M3.tsx
frontend/src/main.tsx
frontend/src/style.css
pyproject.toml
scripts/export_schemas.py
scripts/build-frontend.ps1
scripts/normalize_m3.py
scripts/run_m3_demo.py
scripts/serve_m3_demo.py
```

本地运行产物（被既有 .gitignore 忽略）：正式库无损 schema 升级、迁移前备份、独立演示 SQLite、前端 dist，不纳入 Git 提交。最终后端结论依据用户提供的 313 项全量通过记录，前端结论依据本次实际构建；较早 JUnit 与演示产物按上述时间及范围保留。
