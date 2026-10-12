# RuleForge M1+ 数据基础强化验收报告

日期：2026-10-12。目标分支：main。本次基于工作区已有未提交的模型草稿增量完成，没有自动提交或推送。

## 交付结论

五类强类型标准化记录、四种装备定义、通用来源验证、离线 Extractor Registry、候选验证/审核/发布服务和 SQLite v2 迁移已实现。现有真实 xParse 产物生成 10 条记录，全部为 validated / review_required / reference_only，未批准、未发布、未授予执行能力。皮甲 `srd51.ac.leather` 的既有计算/API 保持可用。

原始 PDF、403 页 JSON、manifest、SHA-256 与日志保留；本次没有调用 xParse 服务或消耗解析额度。没有实现完整 M2。

## 实施前检查与增量策略

- main 工作区原有 README、validation-report 改动，catalog 模型、rules/sources 草稿及差距说明等未提交文件；保留并接续。
- 重新运行历史测试得到 47 passed，而非直接采用旧报告数字。
- 保留 domain.Equipment、原皮甲抽取器、DSL 求值器和 API 响应；通用目录独立扩展。
- 原运行环境的沙箱进程/写入工具初始化失败，改用经授权的本地 PowerShell/Python 完成工作区操作。

## 逐文件代码说明

| 文件 | 改动与影响 |
|---|---|
| backend/ruleforge/rules/sources.py | 接续通用 SourceReference 草稿；定义规则集、状态、标识符、页码与表格位置约束 |
| backend/ruleforge/catalog/equipment.py | 接续四种装备定义草稿；严格分型、骰子、明确货币/重量单位、DEX 策略；不替换角色 Equipment |
| backend/ruleforge/catalog/models.py | 接续五类记录草稿；增加嵌套 source_id/source_ids 的集合校验；载荷和来源关系不能悬空 |
| backend/ruleforge/rules/models.py | 保留旧 RuleRecord 三来源封装；增加 LeatherRuleRecord 与通用 NormalizedRuleRecord 引用 |
| backend/ruleforge/ingestion/evidence.py | 复用 checked_file/json_pointer/verify_span；严格拒绝负数、非规范数组索引及无效 ~ 转义；新增 verify_reference 验证身份、页归属、章节、坐标、Footer、表格位置 |
| backend/ruleforge/ingestion/provenance.py | 从 xParse metadata.children_ids 提取真实标题祖先，不猜测章节 |
| backend/ruleforge/ingestion/tables.py | HTML 表格转逻辑网格，保留 row/column、原单元格位置及 rowspan/colspan；保留 br 词间空格 |
| backend/ruleforge/ingestion/pipeline.py | 离线类别注册表、唯一匹配的受控抽取器、类型候选、验源与失败报告；识别不清则失败，不填造数据 |
| backend/ruleforge/catalog/service.py | 版本化候选管理、完整性摘要、验证报告、显式审核记录、发布与重新验源读取；无通用执行适配器 |
| backend/ruleforge/persistence/migration_v2.sql | 追加四张目录相关表、FK、JSON CHECK、类型/版本索引；不删除旧表 |
| backend/ruleforge/persistence/db.py | BEGIN IMMEDIATE 内按 user_version 迁移；v1→v2 无损、重复初始化幂等、失败回滚、未来版本拒绝 |
| backend/ruleforge/rules/service.py | 只调整已有 parse_run 的幂等登记，并核对文档及 raw 指纹；目录先导入后原皮甲仍能发布，其他执行门禁保留 |
| backend/tests/test_catalog.py | Schema、分型、骰子、规则集、来源、完整性、审核门禁、幂等、迁移/回滚、真实抽取和历史兼容性测试 |
| scripts/normalize_catalog.py | 离线入口；支持 --root、--run-id、--category，失败退出码 1 |
| scripts/export_schemas.py | 保留旧 Schema，追加通用来源/装备联合/五类记录/记录联合 Schema |
| pyproject.toml | 包数据增加 migration_v2.sql；没有新增第三方运行依赖 |
| README.md | 保留已有改动，追加 M1+ 使用入口和限制 |
| docs/architecture.md | 追加新模块、双路径发布、迁移、信任边界与状态说明 |
| docs/rule-coverage.md | 逐项区分已抽取目录、可执行规则与未来功能 |
| docs/model-and-normalization-gaps.md | 保留原差距记录，标明其为实施前快照并链接当前报告 |
| docs/testing.md / docs/validation-report.md | 追加本次真实测试范围和结果，不覆盖历史记录 |
| docs/m1-enhancement-report.md | 本报告；包含真实样本核心字段与逐来源完整哈希 |

新增 JSON Schema：`source-reference.schema.json`、`equipment-definition.schema.json`、`normalized-record.schema.json`、`equipment-record.schema.json`、`spell-record.schema.json`、`class-record.schema.json`、`condition-record.schema.json`、`general-rule-record.schema.json`，均位于 docs/schemas。旧九份 Schema 保留。

## 数据结构与关系

- 通用 `catalog.models.RuleRecord`：id、ruleset、record_version、record_type、canonical_name、aliases、source_ids、extraction_run_id、field_sources、validation_status、review_status、execution_status、schema_version。五个子类用 record_type 做 discriminated union。
- `SourceReference`：document_id 为 PDF SHA-256；run_id 为解析任务；element_pointer / json_pointer / element_id 精确定位；物理页和页 pointer 成对可空；唯一数字 Footer 才记录印刷页；带原文、SHA-256、章节、可选坐标和表格位置。
- `EquipmentDefinition`：公共元数据、来源、带单位的 cost/weight、审核状态。四种子类是 Weapon / Armor / Shield / AdventuringGearDefinition。价格与重量以十进制字符串存储，避免二进制浮点；单位分别 cp/sp/ep/gp/pp、lb，武器射程 ft。
- `ArmorDefinition`：light/full、medium/capped（cap=2）、heavy/none 明确区分；不统一套用 base_ac+DEX。Shield 是独立类型。普通冒险装备无伤害或 AC 必填项。
- `SpellRecord`：基础字段、成分、描述、原文效果、可选伤害骰；不会将复杂文本编译执行。
- `ClassRecord`：生命骰、熟练、表头、1–20 级行、带来源的单元格及特性引用；保留额外资源列。Barbarian 的 Rages 和 Rage Damage 未压缩掉。
- `ConditionRecord`：原始描述、效果、适用/解除条件和关联规则；不推断未出现的解除办法。
- `GeneralRuleRecord`：类别、触发、前提、条件、结算步骤、效果和关联规则；execution_status 位于记录公共层。

```text
documents ──< parse_runs ──< source_references
                               ^
normalized_records (id,version) ──< record_sources
              └──< review_decisions

v1 的 source_spans / rules / rule_sources / verifications 等表继续保留。
```

装备定义就是 normalized_records 中的强类型 payload，无需重复 equipment_definitions 表。当前仅 srd-5.1，暂不建无实际额外元数据的 rulesets 表。记录版本 record_version、格式版本 schema_version、规则集 ruleset、解析任务 extraction_run_id 与标准化批次 normalization_id 明确分开。

## 校验、审核、发布与执行边界

1. create_candidate：只接受 extracted + review_required + reference_only/unsupported。来源集合必须完全匹配；真实引用入库前严格验源。同 ID/版本/内容重复提交幂等；修改内容必须新建记录版本。
2. validate_candidate：Pydantic、记录哈希、全部来源、物理页、原始文件和 manifest 哈希校验；保存成功或失败报告。validated 表示结构与证据一致，**不表示语义已人工审核**。
3. review_candidate：明确记录 reviewer、reason 和 approved/rejected 决定；批准需当前验证成功，决定绑定证据摘要。测试中的批准仅发生在临时数据库，不涉及实际样本。
4. publish_record：验证、批准、完整来源和审核摘要必须一致；目录目前只发布 reference_only/unsupported。approval 不提供执行权限。
5. get_record/list_records：默认用于管理候选；`published_only=True` 只返回发布记录并重新验源。已发布记录复验失败会撤销发布，回到待审核。
6. 计算仍只走原 rules.service：publish、load_verified、calculate_ac；三来源、DSL 哈希、限定上下文和固定数值用例全部保留。

SHA 用于发现证据或内容的意外篡改，沿用 M1 的本地信任边界；不是针对拥有数据库与文件全部写权限的管理员的数字签名系统。

## 真实样本和来源

所有样本来自既有 `data/runs/srd51-full-001/raw/SRD_CC_v5.1.json`，文档为 `data/sources/SRD_CC_v5.1.pdf`（D&D 5E SRD 5.1，2014 体系）。

- 官方来源：[SRD 5.1 PDF](https://media.dndbeyond.com/compendium-images/srd/5.1/SRD_CC_v5.1.pdf)
- 文档 SHA-256：`2504d2a0abb0a4d491a939be4f17910a2dde0312570ab8d208080225ccf0a1f0`
- 原始 JSON SHA-256：`9473d981252593c3a554255b02b41e9435d2ec884399dcff4def580ca3ad841e`
- 所有样本状态：`validation_status=validated`、`review_status=review_required`、`execution_status=reference_only`。
- 完整 payload、SourceReference 和验证结果见 `data/normalized/m1plus/<稳定ID>.json`。表格引用的 quote 哈希覆盖整个原始 HTML 元素，table_location 指定具体单元格，二者一起验证。

### srd51.class.barbarian

类型：class；名称：Barbarian；审核状态：`review_required`。

```json
{
  "hit_die": {
    "expression": "1d12"
  },
  "proficiencies": {
    "armor": "Light armor, medium armor, shields",
    "weapons": "Simple weapons, martial weapons",
    "tools": "None",
    "saving_throws": [
      "Strength",
      "Constitution"
    ],
    "skills": "Choose two from Animal Handling, Athletics, Intimidation, Nature, Perception, and Survival"
  },
  "progression_columns": [
    "Level",
    "Proficiency Bonus",
    "Features",
    "Rages",
    "Rage Damage"
  ],
  "levels": [
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20
  ],
  "level_11_features": [
    "Relentless Rage"
  ]
}
```

| 来源 ID | PDF 物理页 | JSON Pointer | 原文片段 SHA-256 |
|---|---|---|---|
| `srd51-full-001:element:175` | 8 | `/data/elements/175/text` | `3a303970a53b0626e522012d24d33d00ab7c6bdc035b31b41d87f1db7e524356` |
| `srd51-full-001:element:177` | 8 | `/data/elements/177/text` | `bf8b218ba5455e245f5c5ca2a259fde3c771be8c1f3b4618fd0669ddadf2d10d` |
| `srd51-full-001:element:179` | 8 | `/data/elements/179/text` | `31575fff83679cc3443d821a21f24900fd58a51db9322fb161433fd6c660ba86` |
| `srd51-full-001:element:183` | 8 | `/data/elements/183/text` | `548c02b451aa8552bf3d840a100014a3737e464c0ae2c4fd0df846e5f897f5e5` |
| `srd51-full-001:element:184` | 8 | `/data/elements/184/text` | `1e1e202a452d6c199064d28029ca87c25036c1bda411703621050be145d0feaf` |
| `srd51-full-001:element:185` | 8 | `/data/elements/185/text` | `e4e3ef85353b779281a6c5506a6adf2b5208653e3d5f7172bc6a2c375823b149` |
| `srd51-full-001:element:186` | 8 | `/data/elements/186/text` | `19068e142589bbd897b5c2cdc2a1ec8699faa18181caaf3a57bd75d3c42c78a0` |
| `srd51-full-001:element:187` | 8 | `/data/elements/187/text` | `d857e7a3f4bc7c53392d369fa9f7fcb5d4f04d5375dd5272235ba8426cb13fe3` |
| `srd51-full-001:element:194` | 8 | `/data/elements/194/text` | `f21ad83427794bdaaa5b15daf3dbfbce44ba2c13b69fee216563e9d590c060d6` |
| `srd51-full-001:element:195` | 8 | `/data/elements/195/text` | `a7ab7bfeb62088ef2210a01be78c32acd5d8bd0c3fb376adb1e4ecc85f7304d9` |

完整记录：[JSON](../data/normalized/m1plus/srd51.class.barbarian.json)

### srd51.condition.blinded

类型：condition；名称：Blinded；审核状态：`review_required`。

```json
{
  "effects": [
    {
      "kind": "reference_text",
      "text": "·A blinded creature can't see and automatically fails any ability check that requires sight.",
      "source_ids": [
        "srd51-full-001:element:12248"
      ]
    },
    {
      "kind": "reference_text",
      "text": "·Attack rolls against the creature have advantage, and the creature's attack rolls have disadvantage.",
      "source_ids": [
        "srd51-full-001:element:12249"
      ]
    }
  ],
  "removal_conditions": [
    "A condition lasts either until it is countered (the prone condition is countered by standing up, for example) or for a duration specified by the effect that imposed the condition."
  ]
}
```

| 来源 ID | PDF 物理页 | JSON Pointer | 原文片段 SHA-256 |
|---|---|---|---|
| `srd51-full-001:element:12247` | 358 | `/data/elements/12247/text` | `f37106e829dc9e8c3d7443e412833293b9dde7a8b5e0e092209e47f3aff59306` |
| `srd51-full-001:element:12248` | 358 | `/data/elements/12248/text` | `8748c124d2940839b60eca3a1921da09aa7a8133c6adb14ebbdbc90b9639f6af` |
| `srd51-full-001:element:12249` | 358 | `/data/elements/12249/text` | `8a2b2069eca69cc30bf1e0e250692d00af4e9a84335acdcb16396445b2276e0f` |
| `srd51-full-001:element:12244` | 358 | `/data/elements/12244/text` | `92d1391dc10b419fd9fdcb7245ca5fa04f267f03b9f7021635661490b44afb7b` |

完整记录：[JSON](../data/normalized/m1plus/srd51.condition.blinded.json)

### srd51.equipment.chain-mail

类型：equipment；名称：Chain mail；审核状态：`review_required`。

```json
{
  "equipment_type": "armor",
  "cost": {
    "amount": "75",
    "unit": "gp"
  },
  "weight": {
    "amount": "55",
    "unit": "lb"
  },
  "armor_category": "heavy",
  "base_ac": 16,
  "dexterity_modifier_policy": "none",
  "dexterity_modifier_cap": null,
  "strength_requirement": 13,
  "stealth_disadvantage": true,
  "don_time": {
    "amount": 10,
    "unit": "minute"
  },
  "doff_time": {
    "amount": 5,
    "unit": "minute"
  }
}
```

| 来源 ID | PDF 物理页 | JSON Pointer | 原文片段 SHA-256 |
|---|---|---|---|
| `srd51-full-001:element:1647:r10c0` | 64 | `/data/elements/1647/text` | `d0bd372b33a89b44f6ff6060da320013afe00c2e845c7925840729174e800b8d` |
| `srd51-full-001:element:1640` | 63 | `/data/elements/1640/text` | `012a5acea14410cb93d59a341d2e99b8335db01502390ac61d5cdb1401ebbc5d` |
| `srd51-full-001:element:1638` | 63 | `/data/elements/1638/text` | `891abeb373e3a983e141717f9692dad30269ea56e311b6a8ef960e10612c3301` |
| `srd51-full-001:element:1653:r3c0` | 64 | `/data/elements/1653/text` | `28bc940f8fc061fad17c4d84e1a68560f8af66ad7459a5cc56d1a729ad7cca77` |

完整记录：[JSON](../data/normalized/m1plus/srd51.equipment.chain-mail.json)

### srd51.equipment.chain-shirt

类型：equipment；名称：Chain shirt；审核状态：`review_required`。

```json
{
  "equipment_type": "armor",
  "cost": {
    "amount": "50",
    "unit": "gp"
  },
  "weight": {
    "amount": "20",
    "unit": "lb"
  },
  "armor_category": "medium",
  "base_ac": 13,
  "dexterity_modifier_policy": "capped",
  "dexterity_modifier_cap": 2,
  "strength_requirement": null,
  "stealth_disadvantage": false,
  "don_time": {
    "amount": 5,
    "unit": "minute"
  },
  "doff_time": {
    "amount": 1,
    "unit": "minute"
  }
}
```

| 来源 ID | PDF 物理页 | JSON Pointer | 原文片段 SHA-256 |
|---|---|---|---|
| `srd51-full-001:element:1647:r4c0` | 64 | `/data/elements/1647/text` | `d0bd372b33a89b44f6ff6060da320013afe00c2e845c7925840729174e800b8d` |
| `srd51-full-001:element:1631` | 63 | `/data/elements/1631/text` | `fa1b124e648d80e38499a815240153dbea90f66688e31d87b6ea5e544b20220a` |
| `srd51-full-001:element:1629` | 63 | `/data/elements/1629/text` | `6a21d73f9c4a9913148e148194947a7690c154c5ceeb898595a820489ac0ab8c` |
| `srd51-full-001:element:1653:r2c0` | 64 | `/data/elements/1653/text` | `28bc940f8fc061fad17c4d84e1a68560f8af66ad7459a5cc56d1a729ad7cca77` |

完整记录：[JSON](../data/normalized/m1plus/srd51.equipment.chain-shirt.json)

### srd51.equipment.dagger

类型：equipment；名称：Dagger；审核状态：`review_required`。

```json
{
  "equipment_type": "weapon",
  "cost": {
    "amount": "2",
    "unit": "gp"
  },
  "weight": {
    "amount": "1",
    "unit": "lb"
  },
  "proficiency_category": "simple",
  "attack_category": "melee",
  "damage_dice": {
    "expression": "1d4"
  },
  "damage_type": "piercing",
  "weapon_properties": [
    "finesse",
    "light",
    "thrown"
  ],
  "normal_range": 20,
  "long_range": 60
}
```

| 来源 ID | PDF 物理页 | JSON Pointer | 原文片段 SHA-256 |
|---|---|---|---|
| `srd51-full-001:element:1692:r1c0` | 66 | `/data/elements/1692/text` | `45748e198f091bc8fed6fb05eca669048d07585f3f257dad71285d39db615145` |
| `srd51-full-001:element:1689` | 65 | `/data/elements/1689/text` | `4520d9e37fd67ccae096dfd8d02c8b1c31b81883e89f38685529025ae452c481` |

完整记录：[JSON](../data/normalized/m1plus/srd51.equipment.dagger.json)

### srd51.equipment.leather

类型：equipment；名称：Leather；审核状态：`review_required`。

```json
{
  "equipment_type": "armor",
  "cost": {
    "amount": "10",
    "unit": "gp"
  },
  "weight": {
    "amount": "10",
    "unit": "lb"
  },
  "armor_category": "light",
  "base_ac": 11,
  "dexterity_modifier_policy": "full",
  "dexterity_modifier_cap": null,
  "strength_requirement": null,
  "stealth_disadvantage": false,
  "don_time": {
    "amount": 1,
    "unit": "minute"
  },
  "doff_time": {
    "amount": 1,
    "unit": "minute"
  }
}
```

| 来源 ID | PDF 物理页 | JSON Pointer | 原文片段 SHA-256 |
|---|---|---|---|
| `srd51-full-001:element:1647:r0c0` | 64 | `/data/elements/1647/text` | `d0bd372b33a89b44f6ff6060da320013afe00c2e845c7925840729174e800b8d` |
| `srd51-full-001:element:1626` | 63 | `/data/elements/1626/text` | `e1733e08dc0006aa8b2e93b1f7faf1c83e801a404d75642a447eca55887e1822` |
| `srd51-full-001:element:1624` | 63 | `/data/elements/1624/text` | `bf031b9380e2200c6744af5a2d7284034e65032c147cb411bca216868d13383a` |
| `srd51-full-001:element:1653:r1c0` | 64 | `/data/elements/1653/text` | `28bc940f8fc061fad17c4d84e1a68560f8af66ad7459a5cc56d1a729ad7cca77` |

完整记录：[JSON](../data/normalized/m1plus/srd51.equipment.leather.json)

### srd51.equipment.shield

类型：equipment；名称：Shield；审核状态：`review_required`。

```json
{
  "equipment_type": "shield",
  "cost": {
    "amount": "10",
    "unit": "gp"
  },
  "weight": {
    "amount": "6",
    "unit": "lb"
  },
  "ac_bonus": 2,
  "don_time": {
    "amount": 1,
    "unit": "action"
  },
  "doff_time": {
    "amount": 1,
    "unit": "action"
  }
}
```

| 来源 ID | PDF 物理页 | JSON Pointer | 原文片段 SHA-256 |
|---|---|---|---|
| `srd51-full-001:element:1647:r14c0` | 64 | `/data/elements/1647/text` | `d0bd372b33a89b44f6ff6060da320013afe00c2e845c7925840729174e800b8d` |
| `srd51-full-001:element:1622` | 63 | `/data/elements/1622/text` | `20e3cc7f9cca2dbdc362c8c6a6eafb06235b2b93657aabf9d1c8e340baa40935` |
| `srd51-full-001:element:1653:r4c0` | 64 | `/data/elements/1653/text` | `28bc940f8fc061fad17c4d84e1a68560f8af66ad7459a5cc56d1a729ad7cca77` |

完整记录：[JSON](../data/normalized/m1plus/srd51.equipment.shield.json)

### srd51.equipment.torch

类型：equipment；名称：Torch；审核状态：`review_required`。

```json
{
  "equipment_type": "adventuring_gear",
  "cost": {
    "amount": "1",
    "unit": "cp"
  },
  "weight": {
    "amount": "1",
    "unit": "lb"
  }
}
```

| 来源 ID | PDF 物理页 | JSON Pointer | 原文片段 SHA-256 |
|---|---|---|---|
| `srd51-full-001:element:1748:r43c0` | 69 | `/data/elements/1748/text` | `c27974abdf9abb63078ea42c4e57d6a9dcc9f6c028fd431d20fbc6c9aeb59c70` |
| `srd51-full-001:element:1743` | 68 | `/data/elements/1743/text` | `7bd7ba0b3d4606966449763ea316f2742f9dc7cb05ba4875092b7390247f889a` |

完整记录：[JSON](../data/normalized/m1plus/srd51.equipment.torch.json)

### srd51.general_rule.ability-modifier

类型：general_rule；名称：Ability Scores and Modifiers；审核状态：`review_required`。

```json
{
  "category": "ability_modifier",
  "resolution_steps": [
    "To determine an ability modifier without consulting the table, subtract 10 from the ability score and then divide the total by 2 (round down)."
  ]
}
```

| 来源 ID | PDF 物理页 | JSON Pointer | 原文片段 SHA-256 |
|---|---|---|---|
| `srd51-full-001:element:1873` | 76 | `/data/elements/1873/text` | `b8db48f3024aa3b4ddb9e07a9eefb9c79ff23d4f599bf199a90adfbcd12e5670` |

完整记录：[JSON](../data/normalized/m1plus/srd51.general_rule.ability-modifier.json)

### srd51.spell.magic-missile

类型：spell；名称：Magic Missile；审核状态：`review_required`。

```json
{
  "level": 1,
  "school": "evocation",
  "casting_time": "1 action",
  "range": "120 feet",
  "components": {
    "verbal": true,
    "somatic": true,
    "material": false,
    "material_description": null
  },
  "duration": "Instantaneous",
  "concentration": false,
  "ritual": false,
  "damage": [
    {
      "dice": {
        "expression": "1d4+1"
      },
      "damage_type": "force",
      "per": "dart",
      "source_ids": [
        "srd51-full-001:element:5082"
      ]
    }
  ]
}
```

| 来源 ID | PDF 物理页 | JSON Pointer | 原文片段 SHA-256 |
|---|---|---|---|
| `srd51-full-001:element:5076` | 161 | `/data/elements/5076/text` | `111a74afc067f116ddf6a2e8339eada16814eceb7cfcded7a8e6e44c9fd87e6c` |
| `srd51-full-001:element:5077` | 161 | `/data/elements/5077/text` | `7cc881870b0f2d5cca7a0c5fb920362e026a3eee29f37f2a0648a17d9fb5da32` |
| `srd51-full-001:element:5078` | 161 | `/data/elements/5078/text` | `f5b187c3d8270217bf93a66439fef7a2063779beab85baa728f954a048d7b386` |
| `srd51-full-001:element:5079` | 161 | `/data/elements/5079/text` | `9b14ddefc68228e232419ae1aece9a8f4a51a1fbf89d6923955f74abc59f1a85` |
| `srd51-full-001:element:5080` | 161 | `/data/elements/5080/text` | `fbbc0c062c475665fb2ee321e3a597706b4573eaef8738c8ba20b91d69f51568` |
| `srd51-full-001:element:5081` | 161 | `/data/elements/5081/text` | `542f58d6b4116143c58936daf45f9ef5413375bac99d3d277061c03c8e96f1dd` |
| `srd51-full-001:element:5082` | 161 | `/data/elements/5082/text` | `d30783e63da56b17a7c4d788f7492fdc9dcb048b7a6d9ff2b47ba9258a57db26` |
| `srd51-full-001:element:5083` | 161 | `/data/elements/5083/text` | `79ec4d6d471338ce752dedfa27eb13fb95eabee14d97bc7177c9a9bfff82916b` |

完整记录：[JSON](../data/normalized/m1plus/srd51.spell.magic-missile.json)


## 回归验证

最终完整执行：**133 passed，0 failed，0 errors，0 skipped，1 warning**；JUnit 记录耗时 128.853 秒（终端 pytest 汇总 129.04 秒）。

基线：47 passed；本次新增 86 项。警告为已有 Starlette/httpx 弃用提示。

命令：`.venv\Scripts\python.exe -m pytest -q --junitxml=data/local-checks/m1plus-regression.xml`。[原始 JUnit 结果](../data/local-checks/m1plus-regression.xml)。

最终实库核查：user_version=2；foreign_key_check 无错误；旧 rules=1、source_spans=3；normalized_records=10、source_references=42、review_decisions=0、已发布目录记录=0。再次完整离线导入后仍为 10 条记录，失败项为 0。

原 M1 再次 load_verified 成功，仍为 srd51.ac.leather 与三个来源；实际 calculate_ac：DEX 9 → AC 10，DEX 14 → AC 13。原 PDF、raw JSON、manifest/日志及 normalize.py、dsl.py、domain/models.py、api.py 的 Git 差异检查为空。

测试区分真实证据与构造单测：真实测试只读取已存在的解析产物，或将其原样复制到 pytest 临时目录；骰子表达式、合并单元格、无效 payload 和迁移错误属于明确的单元测试输入。没有生成成功解析的虚构替身。

历史 47 项全部保留，覆盖皮甲 DEX 1/2/9/10/11/14/15/20/30 数值、异常装备拒绝、PDF/raw/manifest/来源/DSL/审核状态篡改拒绝、API 的 200/422/503 行为。新增测试还覆盖目录先导入后皮甲发布、全部 v1 表内容逐行保持、迁移中途失败原子回滚、未来 DB 版本拒绝、重复导入、新版本冲突、嵌套引用、发布后改写拒绝以及失败报告历史留存。

## M2 使用接口

```python
from pathlib import Path
from ruleforge.catalog.service import CatalogService

catalog = CatalogService(Path('.'))
# 管理界面可查看待审核条目。人物/装备消费端应只读显式发布版本。
candidates = catalog.list_records('equipment')
# 由授权审核者完成校验和审核后，才可发布；不会自动获得执行能力。
# catalog.validate_candidate(record_id)
# catalog.review_candidate(record_id, 'approved', reviewer='...', reason='...')
# catalog.publish_record(record_id)
# definition = catalog.get_record(record_id, version=1, published_only=True)
```

人物创建可按规则集和已发布职业定义读取生命骰、熟练及等级进度；角色保存稳定 ID + record_version 引用，不能把装备目录对象直接替换现有 Equipment 状态。装备管理消费 Weapon/Armor/Shield/Gear 类型，并按单位处理重量与价格。AC 模块未来按 dexterity_modifier_policy 选择经过审核的执行模板，单独处理盾牌、熟练和替代公式；战斗模块需要新增受限运行适配器、来源/版本绑定、数值用例及上下文门禁之后才能执行。

## 范围限制与待办

- 完成的是代表性 10 条样本，不是整本 SRD 的所有条目；未新增全文搜索 API、角色创建、战斗引擎或审核 UI。
- 新目录尚无通用 runtime adapter；可执行能力不能靠修改状态获得，原 M1 皮甲之外的计算仍拒绝。
- field_sources 当前多为条目级来源集合；部分字段具备更精细的表格/效果引用，后续可继续细化逐字段映射。
- 职业样本使用明确匹配的双表续接规则；任意跨页/错序表格不在本阶段泛化范围。复杂 OCR 错字保留原文并待人工核对，不偷偷修改原始 JSON。
- 武器模型覆盖 SRD 属性集合；本次真实武器样本为 Dagger，不宣称已抽取全部武器。固定伤害的特殊武器等尚需后续补充类型与样本验证。
- 仍有原环境的 Starlette/httpx 弃用警告；没有为此进行与 M1+ 无关的依赖升级。
- Git 未提交、未推送；data/setup/skill-installation.json 等先存文件未纳入本次功能改写。
