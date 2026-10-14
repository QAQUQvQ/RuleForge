# RuleForge M2 实施与验收报告

日期：2026-10-13。范围：D&D 5E SRD 5.1（2014），本地基础计算内核；没有实现完整战斗回合状态机。

## 交付结论

目录检索、版本化角色与装备、独立执行许可、通用装备 AC、确定性骰子、单次武器攻击、分项伤害与隔离目标 HP 预览已实现，并接入 FastAPI 和 React。完整回归实际得到 **222 passed，0 failed，0 errors，0 skipped，1 warning**；前端 TypeScript / Vite 构建通过。

完整计算链路在独立演示数据库通过。正式数据库保留全部原记录，新增7条待审核候选，当前17条目录记录均未正式审核、未发布、未授予M2运行许可。没有将模拟审核称为真实人工审核，也没有通过改变状态字符串绕过门禁。

尚未完成的来源项是普通无甲基础 AC：现有403页 JSON 未找到可直接支持普通角色“10 + DEX”的原文。运行接口明确拒绝，纯算术向量测试不代表该路径已授权。Fighter 创建覆盖职业部分；种族、背景由调用方另行处理，不能当作完整人物生成器。

## 开发前真实基线

- 分支：`main`；HEAD：`beb2fda45e8bdeaaecd18e62ff0eb0fb8ff97f14`。没有自动 commit 或 push，交付时 HEAD 未变化。
- 工作区原有：README.md 改动；未跟踪的 `data/setup/account-status.json`、`data/setup/skill-installation.json`、`docs/competition/`。保留了这些内容，尤其 README 的参赛资料链接。
- 数据库原为 user_version=2，normalized_records=10，published=0；原 M1 执行规则为1条。
- 已读取指定文档、领域/目录/装备/来源/DSL/服务/数据库/API和现有前后端及测试。沿用项目结构，没有重建项目。
- 实际运行开发前全套 pytest：**133 passed，1 warning，133.54秒**。记录：[m2-before.xml](../data/local-checks/m2-before.xml)。
- 升级前通过 SQLite backup API 保存 `data/local-checks/m2-pre-migration.sqlite3`，没有删除或重新初始化真实数据库。

## 证据与原数据保留

| 产物 | 保持不变的 SHA-256 |
|---|---|
| SRD_CC_v5.1.pdf | `2504d2a0abb0a4d491a939be4f17910a2dde0312570ab8d208080225ccf0a1f0` |
| 403页原始JSON | `9473d981252593c3a554255b02b41e9435d2ec884399dcff4def580ca3ad841e` |
| manifest.json | `c9c2a3ecee32d034b2ac0148cc42593a23a39a01df2f27018e9f85832df026e6` |
| 原M1规范化皮甲产物 | `020bee0748ee379b9ce698cabc7eaac94f3cbad39cc50e0a57c11eefede5a8d2` |

核对记录：[m2-evidence-before.json](../data/local-checks/m2-evidence-before.json)。原 `dsl.py`、`normalize.py` 与皮甲执行服务未修改；M1的原三来源、DSL摘要与数值验证均保留。没有调用 TextIn/xParse 服务或消费解析额度。

对备份进行逐行比较：原10条 normalized_records（包括原validation_json）、原审核历史、documents、parse_runs、rules、rule_sources、source_spans、verifications和原characters均保持原值。新增来源和关联仅追加；原始解析产物不写回。重复M2导入不重写原验证报告。

## 模块实现

| 模块 | 实现与边界 |
|---|---|
| M2-A 检索 | ID、关键词、类别、明确登记别名；返回匹配字段；公共查询只读发布记录，候选视图需本地令牌。来源返回物理页、印刷页、章节、原文、JSON Pointer。小数据量采用字面casefold匹配，未引入FTS或向量库。 |
| M2-B 角色 | 1级Fighter，六维1–30及调整值，熟练+2，HP=10+CON，两个技能、全部护甲/盾牌/简单与军用武器熟练、Defense、Second Wind参考资源、固定合法初始装备。稳定职业与规则引用；创建/读取/编辑/保存/CAS。 |
| M2-C 装备/AC | 装备定义与实例分离；数量、装备位置、角色归属、ID/版本及互斥检查；轻中重甲、盾牌、Defense。熟练后果、力量导致的速度降低、隐匿劣势单独报告。普通无甲来源缺口导致拒绝。 |
| M2-D 骰子/攻击 | 限制语法NdS±整数、七类骰子、注入RNG/固定序列/记录/预算；近战与投掷，属性/熟练/Finesse、优势劣势及抵消、自然1/20。要求调用方确认场景，不推测距离或掩护。 |
| M2-E 伤害/HP | 暴击只增加骰子，固定修正只加一次，独立伤害分量，免疫→0，抗性向下取半后易伤翻倍；同类抗性不叠加。临时HP先吸收、当前HP下限0、溢出与死亡阈值信息保留。 |
| M2-F API/UI | 保留旧皮甲API，增加目录/来源、角色CRUD、装备AC及战斗预览。React四区域可操作，固定骰子和DM目标数据明确标识。错误有稳定code/message。 |
| v3 | 追加runtime_grants与character_equipment，保留原characters表；写事务和版本保护；重复迁移幂等；空M2表可降级，有数据拒绝丢失式回滚。 |

角色的初始方案固定为：Chain mail；Longsword + Shield；两把Handaxe；Explorer's Pack。全部出自Fighter第24页装备选择及66/70页定义，没有把原Barbarian记录冒充Fighter。属性分配、种族加值、背景物品不自动补造；输入为调用方确认后的最终数值。角色资源保存Second Wind剩余次数，但本阶段不执行该特性。

## 新规则与来源验证

所有指针均为真实JSON的 `/data/elements/{index}/text`，来源ID为 `srd51-full-001:element:{index}`，表格定位另带行列后缀。完整逐条source reference及载荷摘要保存在 [templates.json](../backend/ruleforge/combat/templates.json)。物理页与Footer印刷页均来自已有解析证据；章节链保留xParse原关系，可能包含原解析错分组（例如Fighter标题的祖先），不将其改写为经过人工确认的章节名称。

| 新记录 | 来源数量 / PDF页 | 关键元素与验证内容 |
|---|---|---|
| srd51.class.fighter v1 | 18 / 24 | 551生命骰，552一级HP，555–559熟练/技能，562–565初始装备，567一级职业表，574 Defense，584 Second Wind参考；使用真实表格单元格复验。 |
| srd51.equipment.longsword v1 | 1 / 66 | 1692真实武器表行，1d8 slashing、martial melee、versatile 1d10；M2只执行单手伤害。 |
| srd51.equipment.handaxe v1 | 1 / 66 | 1692真实武器表行，1d6 slashing、simple melee、light/thrown、20/60ft。 |
| srd51.equipment.explorers-pack v1 | 1 / 70 | 1761，真实背包内容与10gp价格；没有猜测缺失重量。 |
| srd51.general_rule.m2-armor v1 | 8 / 62–63 | 1616熟练后果、1620力量/速度、1621隐匿、1622盾牌、1624/1629/1638三类护甲策略；结合既有装备表。 |
| srd51.general_rule.m2-attack v1 | 16 / 64–65、76、94–95 | Finesse/Thrown/射程，优势劣势与抵消，攻击总值、自然1/20、近敌射击、5ft触及。 |
| srd51.general_rule.m2-damage v1 | 35 / 96–98、203、257 | 伤害/暴击跨页2424与2427、伤害类型、抗性/易伤顺序、临时HP、0HP与溢出；203/257为免疫概念和防御字段背景。 |

保留并复用的7个模板：Dagger、Leather、Chain shirt、Chain mail、Shield、Torch、Ability Scores and Modifiers。共14个M2固定模板；正式目录另有M1+ Barbarian、Magic Missile、Blinded三个纯参考候选，没有M2运行适配器。

执行模板是代码中的受限适配，不从原文生成代码。逐字原文与结构验证只能证明来源一致，不能替代语义审核。整数伤害向下取整、条件范围、场景输入等采用明确的固定模板解释并通过数值向量约束，正式启用前仍须审核者核对整个语义适配；模拟测试不证明已完成该审核。没有从SRD5.2或3.5E补入规则。

## 审核、发布和运行许可

`CatalogService.create_candidate/validate_candidate/review_candidate/publish_record` 继续管理参考目录。`Runtime.register` 单独完成以下检查：

1. 记录已验证且当前审核决定为approved，并已发布。
2. 当前来源、manifest与记录指纹仍匹配原验证和审核。
3. ID、record_version、载荷SHA及完整来源集合与固定白名单完全一致。
4. 27个固定数值向量实际通过，包括属性、熟练、护甲、攻击、暴击、防御和HP。
5. 许可绑定适配器ID、代码/模板哈希、证据摘要与验证报告；后续执行再次核对。

只改review_status或execution_status不够，删除审核决定、篡改验证报告、改来源关系、替换模板/代码或撤销发布都会拒绝运行。许可表是本机完整性门禁，和M1一样不是对恶意数据库管理员的密码学防护。

| 环境 | 审核 / 发布 / 许可范围 |
|---|---|
| 正式 data/ruleforge.sqlite3 | 17候选、0目录发布、0M2许可；原M1皮甲规则继续独立验证执行。 |
| pytest临时数据库 | 模拟审核，仅测试；不会写回正式数据库。 |
| data/local-checks/m2-demo.sqlite3 | 14固定模板使用SIMULATED-TEST-REVIEW，发布与运行注册后演示；不宣称真实人工审核。 |

正式审批须由授权审核者使用原CatalogService显式记录身份和理由，再调用Runtime.register；本次没有执行该正式流程。没有自动发布HTTP端点。

## API 与错误契约

| 路径 | 功能 |
|---|---|
| GET /api/catalog、/api/search | q、record_type、limit、offset；默认只读发布目录。 |
| GET /api/catalog/{id}、/sources | version参数固定版本详情与来源。 |
| GET /api/admin/catalog、/{id} | X-RuleForge-Admin必须匹配服务端RULEFORGE_ADMIN_TOKEN；默认禁用。 |
| POST /api/characters | 严格CreateCharacter，返回角色、调整值、攻击引用和来源。 |
| GET /api/characters/{id} | 校验当前规则许可后读取；不静默使用已撤销规则。 |
| PATCH /api/characters/{id} | expected_version，编辑姓名、属性、技能、速度或装备；服务计算HP最大值，保持当前HP，超过新最大值时截断。 |
| GET /api/characters/{id}/ac | 角色装备AC，包含Defense及装备后果。 |
| POST /api/evaluate/equipment-ac | 新通用装备基础AC接口，按ID+版本绑定；不默认添加职业特性。 |
| POST /api/combat/preview | 固定/随机骰子单次攻击结算；仅更新返回的隔离目标HP快照。 |
| POST /api/evaluate/ac | 原M1行为不变，皮甲、无盾、无替代公式；原200/422/503约定。 |

M2错误形状：`{"error":{"code":"...","message":"..."}}`。主要代码包括rule_unverified、rule_unpublished、missing_adapter、source_integrity_failed、invalid_equipment、version_conflict、unsupported_context、invalid_dice、invalid_input、not_found和admin_required。没有捕获所有异常后返回成功，也不以默认数值替代缺失规则。

`AttackResult` 与`ResolutionPreview`含全部规则版本、适配器/证据摘要、来源列表、骰值和trace。未提交Command/Event，未建立遭遇轮次或伤害事件幂等语义。

## 端到端演示

运行：`.venv\Scripts\python.exe scripts/demo_m2.py`。完整可复现输入输出见 [m2-demo-result.json](../data/local-checks/m2-demo-result.json)。

创建：STR16、DEX14、CON14、INT10、WIS12、CHA8；1级Fighter，Athletics/Perception，Defense，速度30ft（调用方提供）。初始化HP12/12、临时HP0、熟练+2。初始装备使用上述固定合法选择。

| 步骤 | 实际结果 |
|---|---|
| AC | Chain mail16 + DEX采用0 + Shield2 + Defense1 = 19 |
| 场景 | 单次近战，5ft，可见，无遮挡，无近敌远程机制；DM明确确认。 |
| d20 | 固定15，STR调整+3，熟练+2；总值20，对目标AC14命中，非暴击。 |
| 原始伤害 | Longsword 1d8，固定6 + STR3 = 9 slashing。 |
| 防御 | 隔离目标由DM输入挥砍抗性，floor(9/2)=4。 |
| HP | 目标初始20/20、临时2；临时吸收2，当前20→18，临时2→0。 |
| 来源 | 返回规则/装备版本、JSON Pointer、物理页、印刷页、原文与摘要。 |
| 可重现 | 同一个角色版本、相同请求与骰子流，两次完整结果完全相等。 |

同一已授权隔离库的通用AC测试另验证：Leather/DEX14=13；Chain shirt/DEX18=15；Chain shirt/DEX9=12；Chain mail/DEX9=16；Chain mail+Shield=18。角色AC多出的1来自已选择的Defense，未混淆基础装备验收值。

## 实际验证记录

- 开发前：133 passed，133.54秒。
- 最终全套：**222 passed，0 failed，0 errors，0 skipped，1 warning，443.69秒**。[最终JUnit](../data/local-checks/m2-regression.xml)。其中133个M1/M1+回归和89个M2用例。
- 原迁移测试更新最新版本期望2→3、未来版本样本3→4；保留全部原始无损/回滚约束。
- 前端：`pnpm --dir frontend run build`，tsc --noEmit与Vite7.3.7均成功，29模块；构建产物约235.96kB JS（gzip74.51kB）。
- Schema：`scripts/export_schemas.py`成功，保留原模型并生成M2输入/输出契约。
- 警告：既有Starlette/httpx弃用提示；没有为消除警告擅自升级依赖。
- 中间失败与原因见[testing.md](testing.md)：代码变更使许可失效的3项测试，以及修复前测试自身可变对象污染导致的1项失败；最终没有隐藏失败或跳过。

浏览器验收使用独立库和构建产物进行，实际操作完成：检索Fighter（1条）、展开一级HP来源（PDF/印刷页24，element552）、创建角色（HP12/12、熟练+2）、读取装备并计算AC19、运行固定骰子15,6，显示命中/攻击总值20/伤害4/隔离HP18/临时HP0。[浏览器验收截图](../data/local-checks/m2-browser-combat.jpg)。Windows临时静态检查服务需要正确JavaScript MIME；只对检查进程设置，未改系统配置。日常启动使用既有Vite代理。

最后再次离线导入后，原10条目录及原审核/验证、全部原来源关联保持不变；实库仍17候选、0发布、0M2许可，foreign_key_check为空。实库人物创建实际返回HTTP409 / rule_unpublished。[最终审计JSON](../data/local-checks/m2-final-audit.json)。

## 新增与修改文件

新增后端：

- `backend/ruleforge/ingestion/m2.py`：离线新增候选与固定产物约束。
- `backend/ruleforge/combat/__init__.py`、`errors.py`、`dice.py`、`modifiers.py`、`attacks.py`、`damage.py`：受限确定性纯计算。
- `backend/ruleforge/combat/runtime.py`、`templates.json`、`verification.py`：独立运行许可、完整白名单来源和固定测试。
- `backend/ruleforge/combat/characters.py`、`ac.py`、`service.py`、`demo.py`：事务角色服务、通用AC、预览、明确隔离模拟。
- `backend/ruleforge/m2_api.py`、`backend/ruleforge/persistence/migration_v3.sql`。
- `backend/tests/test_m2.py`、`scripts/normalize_m2.py`、`scripts/demo_m2.py`。

修改后端与配置：`api.py`接入新路由与可选数据库；`catalog/service.py`增加搜索/来源；`domain/models.py`兼容扩展；`ingestion/evidence.py`增加请求内解码缓存但保留每次哈希检查；`persistence/db.py`迁移与安全降级；`backend/tests/test_catalog.py`版本期望；`pyproject.toml`打包新增SQL/模板；`scripts/export_schemas.py`。

前端：新增`frontend/src/M2.tsx`；修改`main.tsx`、`style.css`、`frontend/index.html`。文档：本报告、README、architecture、rule-coverage、testing。

Schema：更新character、creature、combat-state（因为内嵌角色扩展）；新增equipment-instance、create-character、patch-character、attack-context、attack-result、preview-request、resolution-preview、equipment-ac-request、damage-component、damage-defenses。原Command/Event没有假称新增战斗状态机。

本地验收产物：基线/回归JUnit、隔离演示完整JSON、证据摘要、数据库备份与演示库；SQLite文件沿用已有.gitignore，不误当成源代码提交。用户原参赛资料和setup文件未修改。最终全部代码仍在工作区，未暂存/提交/推送。

## 限制和M3复用接口

- 正式数据审核与执行许可仍待完成；普通无甲AC还缺直接来源。正式部署不得把演示审核迁入真实库。
- 仅1级Fighter职业配置；仅Defense可自动结算；没有种族、背景、完整升级或多职业。普通无甲、职业替代AC公式拒绝。
- 已登记武器只支持单手近战与投掷；弹药、双手、重型、触及、特殊武器、额外攻击、法术攻击和复杂掩护拒绝。没有推定完整场景合法性。
- 防御只接受DM明确提供的无条件伤害类型集合，不解析“非魔法且非银”等条件。多分量伤害纯函数可复用，但公开攻击预览只从当前白名单武器构造基础分量，不接受任意可执行公式。
- HP更新为隔离快照。0HP、受伤时已0HP、溢出/即死阈值均保留；死亡、稳定、击昏和怪物死亡政策留待DM/M3，不自动写角色死亡状态。
- 当前引用/来源级哈希复验开销较高，小目录与本地演示可用；没有引入跨请求的可信缓存。
- M3可直接复用`Characters.transaction/load/validate/save`、`ResolutionScope.require/evidence`、`attack`、`damage`、`apply_hp`及类型化结果。仍需实现真实Command→Event→CombatState事务、事件幂等、重放、先攻/回合、反应和持续状态。
