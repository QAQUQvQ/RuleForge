# RuleForge · M2
React + TypeScript / FastAPI / Pydantic / SQLite / pytest。现有 M1 皮甲规则保持兼容；M2 增加目录检索、1 级 Fighter 职业创建、装备、AC 与确定性攻击/伤害预览。正式目录尚未人工审核或授予 M2 运行许可，完整链路在隔离演示库验证。完整战斗状态机及 Homebrew 执行尚未实现。

## 已有真实证据
- 官方 SRD 5.1 CC PDF：403 页，3,158,713 bytes。
- xparse-cli 2.5.0，唯一解析调用使用 **--api free**。
- 实际返回 code=200、success_count=403、403 个 Success 页面、14,164 个元素。
- 原始 JSON：data/runs/srd51-full-001/raw/SRD_CC_v5.1.json（24,161,238 bytes）。
- PDF SHA-256：2504d2a0abb0a4d491a939be4f17910a2dde0312570ab8d208080225ccf0a1f0
- 原始 JSON SHA-256：9473d981252593c3a554255b02b41e9435d2ec884399dcff4def580ca3ad841e
- 原始 stdout/stderr 本次均为空文件，这是 CLI 写目录模式下的实际输出，不是补造的成功日志。
- manifest.json 保留来源、CLI 版本、执行参数、退出码和产物哈希；setup 中保存真实配额、版本、文档信息。
- PDF 完整解析不等于所有 SRD 规则都已结构化/可执行。目前只有皮甲 AC 发布。

## M2 运行与验收

先阅读 [M2 实施报告](docs/m2-implementation-report.md)。以下操作均离线使用已有 JSON，不调用 TextIn。

```powershell
# 实库无损升级 v3，新增候选；不会审核、发布或授予执行权限
.venv\Scripts\python.exe scripts/normalize_m2.py
# 独立数据库，明确模拟审核，只用于本机演示/测试
.venv\Scripts\python.exe scripts/demo_m2.py
```

演示数据库：`data/local-checks/m2-demo.sqlite3`；完整输入、输出与全部来源：`data/local-checks/m2-demo-result.json`。脚本不删除或重置任何数据库；重复执行重新核验并新增演示角色。运行时代码变化会使旧执行许可失效，须重新运行演示准备过程。

启动交互演示后端（新终端；若 8000 已有服务，先由该终端正常停止）：

```powershell
$env:RULEFORGE_DATABASE = (Resolve-Path data/local-checks/m2-demo.sqlite3).Path
# 可选：管理候选视图；请自行设置本地令牌，不要放入 Git
$env:RULEFORGE_ADMIN_TOKEN = 'replace-with-your-local-token'
.venv\Scripts\python.exe -m uvicorn ruleforge.api:create_app --factory --host 127.0.0.1 --port 8000
```

另一终端运行 `.\scripts\start-frontend.ps1`。依次检索 Fighter、创建角色、查看/编辑装备、计算 AC、确认场景输入并运行固定骰子演示。切回正式库时在后端终端移除 `RULEFORGE_DATABASE` 环境变量后重启。正式库新增角色会返回 `rule_unpublished`，这是预期门禁。旧 `/api/evaluate/ac` 继续使用原 M1 证据，只接受皮甲、无盾、无替代公式。

演示：STR16 / DEX14 / CON14，Defense + Chain mail + Shield → AC19；固定骰子 `[15,6]`，Longsword 攻击总值20，对 AC14 命中；伤害9，挥砍抗性后4，临时HP2吸收后目标HP20→18。同一输入可重复得到完全一致结果。结果是 `ResolutionPreview`，不写入战斗事件或正式目标 HP。

通用装备 AC 使用新接口 `/api/evaluate/equipment-ac`：Leather + DEX14 →13；Chain shirt + DEX18 →15；Chain mail →16；加 Shield →18。角色的 Defense 另加1。普通无甲 AC 缺少当前 SRD 提取链的直接来源，因此运行接口拒绝；纯算术测试不等于运行许可。

角色流程覆盖 Fighter 职业部分，使用调用方确认的最终属性和基础速度；不自动生成种族、背景或升级。远程路径目前为已登记武器的投掷攻击；弹药、双手使用、法术及额外攻击明确不支持。

```powershell
.venv\Scripts\python.exe -m pytest -q --junitxml=data/local-checks/m2-regression.xml
.venv\Scripts\python.exe scripts/export_schemas.py
pnpm --dir frontend run build
```

## 首条规则
皮甲、无盾牌、无替代 AC 公式：**AC = 11 + floor((DEX - 10) / 2)**。
DEX=14 得到 AC=13；DEX=9 得到 AC=10。
证据：PDF 第 64 页皮甲表，第 63 页 Light Armor，第 76 页属性调整值。
最初设计的无甲公式未取得同样完整的来源链，因此不发布。无甲、其他护甲、盾牌或替代 AC 公式均明确拒绝。
计算返回规则版本、计算步骤、三段原文与 PDF 页码；每次执行核对原始证据与已验证 DSL。
验证属于受限模板原文校验和数值测试，不冒充人工 DM 审核。Homebrew 必须另行实现人工审核发布。

## 本地运行
在项目根目录操作。后端需要 Python 3.12+；前端需要 Node 20.19+/22.12+（或兼容更高版本）。

### 本机已有环境：直接启动
不要再次执行 `python -m venv .venv`。本项目已有环境曾使用 Python 3.12 创建，当前已修复为匹配 Anaconda Python 3.13.9 的依赖。
```powershell
.\scripts\start-backend.ps1
```
脚本使用项目自己的 .venv，先检查依赖是否能导入，再启动后端。API 文档：http://127.0.0.1:8000/docs
也可直接运行：
```powershell
.venv\Scripts\python.exe -m uvicorn ruleforge.api:create_app --factory --host 127.0.0.1 --port 8000
```
另一个终端启动前端：
```powershell
.\scripts\start-frontend.ps1
```
打开 http://127.0.0.1:5173。开发代理将 /api 发往 8000，后端需另行启动。

如果普通 PowerShell 提示“无法识别 pnpm”，使用上面的启动脚本即可。Codex 的工具环境会提供自带 Node/pnpm 路径，但这些路径未必存在于你的终端 PATH。脚本优先查找已安装的 Node，找不到时使用本机已有的 Codex Node，再直接运行项目内的 Vite；不修改全局 PATH，也不安装任何工具。它要求 `frontend/node_modules` 已存在，新机器仍需先安装依赖。

只检查启动环境可运行 `.\scripts\start-frontend.ps1 -Check`；自定义端口用 `-Port 5174`，指定 Node 用 `-NodePath 'C:\path\to\node.exe'`。端口占用时明确报错，不自动切换。已配置 pnpm 的终端仍可使用原命令 `pnpm --dir frontend run dev`。

### 新机器首次安装
下面的检查会拒绝覆盖已有环境；不要把首次安装步骤用于日常启动。
```powershell
if (Test-Path .venv) { throw "已有 .venv，请直接启动或按下方步骤修复依赖。" }
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "创建虚拟环境失败" }
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw "安装依赖失败" }
.venv\Scripts\python.exe -m pip install --no-deps -e ".[test]"
if ($LASTEXITCODE -ne 0) { throw "安装项目失败" }
.venv\Scripts\python.exe -m ruleforge.cli publish srd51-full-001
if ($LASTEXITCODE -ne 0) { throw "规则发布失败" }
pnpm --dir frontend install --frozen-lockfile
```
这些命令使用已有解析产物，不调用 TextIn。

### Python 版本混用修复
如果在已有 .venv 上用另一版本 Python 再次执行 venv，可能出现解释器已变而旧二进制依赖仍保留的情况。本次错误是 Python 3.13 加载残留的 cp312 Pydantic 扩展。
仅在需要修复时执行：
```powershell
.venv\Scripts\python.exe -m pip install --force-reinstall -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw "依赖修复失败" }
.venv\Scripts\python.exe -c "import pydantic, pydantic_core, fastapi; print('依赖正常')"
```
这只修复项目虚拟环境，不修改 Anaconda 全局依赖。pip 的 “Requirement already satisfied” 不能证明残留二进制兼容当前解释器。
若 npm 官方源出现证书问题，应配置受信证书或可信镜像，不关闭 TLS 校验。本次前端通过 https://registry.npmmirror.com 安装。
生产 dist 需同源反向代理 /api；当前不包含公网部署或身份认证，默认仅监听回环地址。

## 验证
```powershell
.venv\Scripts\python.exe -m pytest -q --junitxml=data/test-results.xml
.venv\Scripts\python.exe scripts/export_schemas.py
pnpm --dir frontend run build
```
真实证据测试读取已保存的实际 JSON，不发送网络请求。缺失真实文件时标记跳过，并明确不能视为 M1 通过。
错误路径单测只构造带有明显测试标记的失败输入，不生成解析成功替身。

## 再次解析
已有完整成功结果，无需重新消费免费配额。重建数据库使用 publish，不使用 parse。
官方 Skill 已安装到 C:/Users/23100/.codex/skills/xparse-parse/SKILL.md，安装记录在 data/setup/skill-installation.json；项目内保留 docs/vendor/xparse-parse/SKILL.md 快照。API 适配器只使用官方 CLI、不重写认证或 HTTP 请求、不允许 paid 参数。
新任务首次 xParse 命令需要技能要求的私有任务上下文文件，调用后删除；Windows 使用当前用户 ACL 代替仅 chmod。
若确实需要新解析，先检查当前技能及配额，按技能错误门处理。项目 CLI 支持：
```text
ruleforge parse --executable <official-xparse-native-executable>
```
此路径固定免费端点，无自动重试；已有失败/运行中记录时拒绝重提，必须先检查原始错误与服务要求。绝不通过删除证据绕过恢复要求。

## 主要文件
- [参赛资料](docs/competition/README.md)：参赛指南原文、配套图片、原始压缩包及要求摘要
- docs/architecture.md：最终模块和信任边界
- docs/schemas/：Pydantic 导出的 Rule / Character / Creature / Item / CombatState / Command / Event JSON Schema
- backend/ruleforge/persistence/schema.sql：实际数据库定义
- docs/rule-dsl.md：已支持 DSL
- docs/testing.md：分阶段测试计划
- docs/rule-coverage.md：覆盖范围
- ATTRIBUTION.md：SRD 署名与派生内容说明
# RuleForge V1.0 项目规划与参赛实施方案

**副标题：基于 TextIn xParse 的 D&D 5E SRD 5.1 可执行规则引擎**  
**文档版本：V1.0 ｜整理日期：2026-10-08｜项目阶段：参赛开发规划**

> 核心定位：把静态规则书转换为可检索、可追溯、可计算、可执行、可扩展的 TRPG 辅助系统。目标参加 TextIn xParse「文档觉醒」AI 应用创新赛·脑洞创意赛道。

## 1. 项目概览

| 项目字段 | 内容 |
|---|---|
| 项目名称 | RuleForge |
| 首版规则 | D&D 5E SRD 5.1（2014 规则体系，不混用 SRD 5.2） |
| 核心用户 | 玩家 PL、地下城主 DM |
| 核心模块 | 文档解析、规则速查、基础人物创建、完整战斗流程、自定义规则导入 |
| 技术路线 | TextIn xParse + Codex + FastAPI + Python 规则引擎 + React + SQLite |
| 部署形态 | 本地优先、支持部署的 Web 应用 |
| 比赛截止 | 2026-10-28 23:59:59 |
| 建议冻结 | 2026-10-23 |

### 1.1 首版产品承诺

首版实现“流程完整”，即遭遇创建→先攻排序→回合推进→行动声明→判定与效果结算→结束战斗→生成日志；不承诺 SRD 5.1 所有特殊能力、法术、反应都自动判定。未覆盖的机制必须提供规则检索、DM 手动裁定和日志记录，不能假装自动支持。

### 1.2 核心创新

1. **规则可执行化**：xParse 将 PDF 提取为内容与表格；经过结构化、验证、规则编译，进入确定性执行引擎。
2. **计算可溯源**：每次 AC、命中、伤害、豁免或状态改变，记录触发规则、计算式、掷骰结果和原文出处。
3. **规则动态扩展**：DM 上传自定义（Homebrew）规则文档，解析、审核后加入知识库，并在受限模板范围内参与运算。

## 2. 产品功能规格与优先级

**优先级定义：** P0 = 参赛版必需；P1 = 有余力完成；P2 = 赛后扩展。

### 2.1 A 模块：SRD 文档解析与规则知识库

| 功能 | 优先级 | 验收产物 |
|---|---|---|
| 官方 SRD 5.1 PDF 导入与解析任务 | P0 | 文档、任务记录 |
| xParse Markdown/JSON 真实解析 | P0 | 真实响应、日志、解析产物 |
| 章节、条目、表格抽取 | P0 | 装备、职业、法术和战斗条目 |
| 文档、章节、页码及原文关联 | P0 | 来源可追溯的条目 |
| Schema 校验和人工复核标记 | P0 | 规则数据状态与错误报告 |
| 规则版本管理（srd-5.1） | P0 | 独立版本命名空间 |
| 多文档批量导入 | P1 | 批量处理与去重 |

验收：参赛演示所用规则均能追溯到解析后的真实 SRD 源文档；不存在为满足演示而伪造的解析响应或页码。

### 2.2 B 模块：规则速查

| 功能 | 优先级 |
|---|---|
| 关键词搜索、全文索引 | P0 |
| 自然语言问题理解及带证据回答 | P0 |
| 战斗、装备、职业、法术等分类浏览 | P0 |
| 点击跳转到来源章节/页码 | P0 |
| 与当前战斗状态关联的规则入口 | P0 |
| 中英文关键词与别名词典 | P1 |

原则：AI 负责理解问题、定位资料、解释规则；规则计算交给确定性引擎。无法从来源中确定的结论必须明确标示为不确定。

### 2.3 C 模块：基础人物创建

| 功能 | 优先级 |
|---|---|
| 六维属性、调整值计算 | P0 |
| SRD 种族、职业、背景选择 | P0 |
| 等级、熟练加值、技能与豁免 | P0 |
| HP、AC、速度、攻击数据 | P0 |
| 武器、护甲和盾牌管理 | P0 |
| 角色保存、读取、编辑 | P0 |
| 基础施法数据与法术位 | P1 |
| 多职业、完整升级流程 | P2 |

端到端先保证 1 级战士、游荡者、法师三个模板可用；数据库和 Schema 保持可扩展。

### 2.4 D 模块：完整战斗流程

**工作流：** 创建遭遇→加入角色与怪物→掷先攻→开始回合→选择行动→合法性检查→计算判定→结算效果→保存日志→下一回合／结束。

| 机制 | P0 必需能力 | 复杂情况方案 |
|---|---|---|
| 先攻 | d20 + 敏捷调整值、排序 | 同先攻由 DM 选择 |
| 行动经济 | 行动、附赠动作、移动、反应消耗 | 特殊动作走扩展或 DM 裁定 |
| 攻击 | 近/远程攻击、熟练值、命中判定 | 场景特例手动修正 |
| 优势/劣势 | 两次 d20 取高/低、相互抵消 | 记录触发来源 |
| AC | 护甲、盾牌、敏捷及明确支持的修正 | 额外效果独立生效 |
| 伤害 | 伤害骰、调整值、暴击、伤害类型 | 组合伤害分项处理 |
| 防御 | 抗性、易伤、免疫及临时 HP | 明确结算顺序 |
| 生命状态 | HP、治疗、0 HP、死亡豁免、稳定 | 保留人工裁定入口 |
| 状态 | 常见状态及持续时间 | 仅自动处理已实现条目 |
| 法术 | 施法命中、豁免、伤害、治疗、资源消耗 | 仅对测试集中受支持的法术自动结算 |
| 日志 | 命令、骰值、规则、结果及状态变化 | 支持 DM 调整与审计 |

**核心限定：** V1.0 战斗流程完整，但法术与特殊能力覆盖采用明确的“已支持清单”；反应插入与持续效果时机应纳入状态机设计，暂时无法自动化的效果交给 DM 决策。

### 2.5 E 模块：Homebrew 自定义规则导入

| 导入等级 | 能力与范围 | 优先级 |
|---|---|---|
| 知识型 | 导入文档为检索条目 | P0 |
| 数据型 | 通过 Schema 的装备、怪物及简单状态 | P0 |
| 执行型 | 受限的固定加值、伤害骰替换、附加伤害模板 | P0（受限） |
| 任意规则自动执行 | 从任意自然语言生成通用可执行逻辑 | P2 |

输入→xParse→规则草案→字段检查→DM 审核→发布→在角色/战斗中使用。禁止直接执行 AI 生成的 Python/JavaScript；使用白名单指令与受限规则 DSL。

## 3. 技术架构

### 3.1 技术选型

| 层次 | 选型 | 职责 |
|---|---|---|
| 开发 Agent | Codex | 工程设计、编码、测试、调试 |
| 文档解析 | TextIn xParse Skills/CLI/API | 结构化提取，保留真实解析证据 |
| 前端 | React + TypeScript | 规则、角色、战斗和导入界面 |
| 后端 | Python + FastAPI | API、权限、任务编排、服务逻辑 |
| 数据验证 | Pydantic | 输入及规则结构约束 |
| 规则引擎 | Python 纯函数 + 状态机 | 确定性判定、状态转换 |
| 存储 | SQLite + 文件存储 | 角色、规则、遭遇、事件与文档 |
| 搜索 | SQLite FTS5 | 全文检索；后续按需引入语义索引 |
| AI | 可配置大模型 API | 问句解析、候选抽取、自然语言解释 |
| 测试 | pytest | 规则单测、集成测试、回归测试 |

架构形式：模块化单体。优先完成可信规则引擎，不引入微服务、Kubernetes 或重型向量数据库。

### 3.2 分层和数据流

```text
SRD 5.1 PDF / 授权的 Homebrew PDF
        ↓
TextIn xParse（官方技能、CLI 或 API）
        ↓
原始 Markdown / JSON + 日志 + 来源信息
        ↓
标准化抽取 → Pydantic 验证 → 审核与版本发布
        ├──────────────→ 规则知识库 → 搜索 / 有依据的问答
        └──────────────→ 受限规则 DSL → 确定性规则引擎
                                          ↓
                             战斗状态机 + 命令/事件日志
                                          ↓
                               React Web 跑团控制台
```

### 3.3 五步规则管线

1. **Parse（解析）**：由 xParse 生成文档内容、表格和章节信息；留存原始产物。
2. **Normalize（标准化）**：归一为装备、职业、法术、状态、规则引用等领域数据。
3. **Compile（编译）**：转换为受限操作、条件和效果配置，不生成任意可执行程序。
4. **Validate（校验）**：Schema 校验、来源复核、规则单测、DM 审核。
5. **Execute（执行）**：根据当前状态、用户命令、骰值和已发布规则确定结算结果。

### 3.4 规则 DSL 示例（项目内部格式，不是 xParse 输出）

```json
{
  "id": "srd51.condition.prone.melee",
  "ruleset": "srd-5.1",
  "category": "attack_modifier",
  "conditions": [
    "target.has_condition:prone",
    "attacker.distance_ft<=5"
  ],
  "effect": {
    "type": "attack_advantage",
    "value": true
  },
  "source": {
    "document_id": "srd-5.1",
    "section": "Conditions: Prone",
    "page": null
  },
  "review_status": "pending"
}
```

真实实现需要严格的 DSL 解析器、执行时机、优先级和冲突机制；`page` 仅在从文档获得真实页码映射后填充。

### 3.5 战斗状态与事件模型

命令示例：`AttackCommand`、`CastSpellCommand`、`MoveCommand`、`EndTurnCommand`、`ApplyEffectCommand`。

```text
命令 + 当前战斗状态
    → 合法性与资源校验
    → 规则查找、掷骰和修正值结算
    → 效果与持续时间处理
    → 新状态 + 事件日志 + 来源引用
```

战斗状态应覆盖：轮数、先攻、行动者、HP、AC、速度、位置、行动额度、反应资源、状态、持续效果、法术位、骰子记录、DM 裁定记录。特别注意借机攻击等反应必须在触发时机插入，而非直接排在普通回合后。

### 3.6 推荐目录

```text
ruleforge/
├── frontend/
│   ├── pages/{rules,characters,combat,homebrew}/
│   └── components/
├── backend/
│   ├── api/
│   ├── ingestion/             # xParse 适配、标准化、来源索引
│   ├── rules/{schema,compiler,evaluator}/
│   ├── combat/{dice,initiative,actions,attacks,damage,conditions,spells,state_machine}.py
│   ├── characters/
│   ├── persistence/
│   └── tests/
├── data/{raw,normalized,fixtures}/
├── docs/{architecture,competition}/
├── docs/rule-coverage.md
└── README.md
```

`rule-coverage.md` 必须逐条标记：自动执行、部分执行、仅检索、未支持。

## 4. 开发排期与里程碑

**参赛截止：2026-10-28 23:59:59；建议 10 月 23 日功能冻结，10 月 27 日前提前提交。**

| 日期 | 阶段 | 主要工作 | 验收里程碑 |
|---|---|---|---|
| 10/08—10/11 | M1 文档解析与数据模型 | 官方 SRD 5.1、xParse 解析、来源映射、核心 Schema | 一条规则完成真实解析与验证，可被程序求值 |
| 10/12—10/16 | M2 角色、检索、战斗基础 | 角色模型、FTS 检索、骰子、先攻、AC、命中、伤害 | 角色可加入遭遇并完成基础攻防结算 |
| 10/17—10/21 | M3 完整战斗流程 | 回合状态机、行动资源、状态、死亡豁免、法术基础、日志 | 2 名 PL + 2 名怪物完整运行至战斗结束 |
| 10/22—10/23 | M4 Homebrew 与冻结 | PDF 导入、字段校验、审核、可执行武器模板 | 自定义武器解析并参与战斗；功能冻结 |
| 10/24—10/28 | M5 评测与提交 | 测试、录屏、PDF 文档、调用证明、提交 | 10/27 完成材料并尽量提前提交 |

### 4.1 M1：10 月 8—11 日

- 确认下载 SRD 5.1 CC BY 4.0 官方文档，保证版本唯一。
- Codex 安装并调用 xParse 官方 Skill；检查凭证、额度、大小限制。
- 解析护甲、武器、职业表、状态及战斗规则；保留请求/响应及日志。
- 设计 `Rule`、`Item`、`Character`、`Creature`、`CombatState` Schema。
- 建立数据库和自动测试；至少实现一条来源可追溯的 AC 规则。

### 4.2 M2：10 月 12—16 日

- 规则查询、来源查看、角色创建和保存。
- 实现骰子引擎；可注入固定随机序列用于测试重放。
- 先攻、攻击、命中、优势/劣势、AC、伤害及临时 HP。
- 每项计算记录规则 ID、公式、骰值和状态变更。

### 4.3 M3：10 月 17—21 日

- 完成战斗回合、行动资源、移动和结束判定。
- 处理基础状态、治疗、0 HP、死亡豁免及手动调整。
- 接入已验证的基础攻击/豁免法术、法术位管理。
- 保留反应触发时机、持续效果及 DM 裁定日志。

### 4.4 M4：10 月 22—23 日

- Homebrew PDF 上传、xParse 解析、规则草案与审查 UI。
- 支持自定义武器/怪物及限定模板的可执行效果。
- 在实际战斗里使用新导入的规则，形成前后对比证明。
- 冻结功能，停止开发新特性。

### 4.5 M5：10 月 24—28 日

- 固化测试、复核准确率与来源。
- 录制“文档上传→解析→规则编译→角色创建→战斗→Homebrew”的完整流程。
- 完成不少于 1000 字的参赛说明 PDF，附 xParse 配置/调用截图。
- 提供可访问应用链接或完整录屏至少一种。
- 核对作品原创性、署名与资料授权；在官方表单提交。

## 5. 测试与验收

以下属于**内部建议指标**，不是赛事官方评分规则，也不是已实测结果。

| 指标 | 建议验收目标 |
|---|---|
| 已声明支持的 P0 规则 | 固定测试集中 100% 通过 |
| 战斗流程 | ≥3 种预设遭遇可成功运行 |
| 规则溯源 | 演示用规则 100% 有有效来源 |
| Homebrew | ≥2 个获授权的不同结构 PDF 成功解析并导入 |
| 异常管理 | 非法动作、缺失规则和解析失败均有明确提示 |
| 可复现性 | 固定骰子序列可重放一致的结果 |

三种演示测试：A. 战士对战哥布林（先攻、AC、伤害、HP）；B. 法师战斗（受支持法术、豁免、资源、状态）；C. Homebrew 武器（PDF→审核→装备→计算生效）。

## 6. 风险与控制策略

| 风险 | 控制措施 |
|---|---|
| PDF 表格误识别 | 用人工标注样本验证字段；保留原文与 Schema 错误报告 |
| 大模型幻觉影响规则 | AI 仅用于检索、解释与候选抽取；计算由确定性引擎执行 |
| 法术和特殊动作规则过广 | 发布规则覆盖清单；不支持时要求 DM 裁定 |
| 状态或资源重复消耗 | 状态机 + 命令合法性检查 + 原子事件日志 |
| AI 生成恶意执行代码 | 禁止执行生成代码；仅编译白名单 DSL |
| 工期超限 | 10/21 必须达成战斗闭环；10/23 功能冻结 |
| 版权及规则版本混用 | 只以 CC BY 4.0 的 SRD 5.1 为基础；授权后方可使用其他文档 |

## 7. 参赛交付清单

- [ ] 作品名称与作品描述（RuleForge）。
- [ ] 作品说明 PDF 不少于 1000 字，包含介绍、技术方案、处理流程、效果。
- [ ] xParse 真实安装、配置和调用截图；保留原始解析文件与日志。
- [ ] 可访问的运行链接或完整演示录屏（至少一种）。
- [ ] 规则引用、计算测试与前后对比材料。
- [ ] 原创性、CC BY 4.0 署名与 Homebrew 文档授权核对。
- [ ] 2026-10-28 23:59:59 前完成官方提交，争取 10/27 提前提交。

## 8. Codex 首轮任务说明

> 开发 RuleForge V1.0：基于 TextIn xParse 和 D&D SRD 5.1 的规则检索、基础人物创建、完整战斗流程与 Homebrew 导入系统。技术栈 React + TypeScript、FastAPI、Pydantic、SQLite、pytest。第一阶段只实现项目骨架、官方 SRD 5.1 PDF 的真实 xParse 解析、来源追溯、规则数据模型及至少一条经验证的 AC 规则。必须保留实际解析产物、日志和错误；未经允许不得调用付费 API；禁止模拟解析成功。规则计算必须与 AI 文本生成分离；禁止直接执行大模型生成的代码。先设计模块、数据库 Schema、规则 DSL 草案及分阶段测试计划，再按里程碑编码；暂缓复杂前端。

## 9. 官方资源与长期维护

- 大赛官网：https://builderx.csdn.net/activity-site/docawakening/pages?utm_medium=ad.986
- 参赛指南：https://hibg5d5t9s.feishu.cn/wiki/ByVNwLxZKiPf6AkDU7Hc2kGHnbh
- 作品提交：https://marketing.csdn.net/questions/Q2608311543171467490
- TextIn xParse Skills：https://github.com/intsig-textin/xparse-skills
- SRD 官方入口：https://www.dndbeyond.com/srd

**资料说明：** 本文以当前会话已经确定的产品设计及项目内已整理的比赛指南为基础，是实施方案而非软件已实现情况。xParse 命令参数、账户免费额度和参赛表单字段以实际调用及官方最新说明为准。

**维护建议：** 每次迭代同步更新 `docs/rule-coverage.md`、里程碑完成状态、规则验证用例、xParse 调用证据，以及本文版本号和修订日期。

## M1+ 数据基础（2026-10-12）
在现有 M1 上增加五类强类型目录、装备分型、来源验证、候选审核/发布服务及 SQLite v2 无损迁移。真实样本 10 条，全部待人工审核、仅供检索；既有皮甲 AC 的 API 和执行范围保持不变。

```powershell
.venv\Scripts\python.exe scripts/normalize_catalog.py
.venv\Scripts\python.exe scripts/export_schemas.py
.venv\Scripts\python.exe -m pytest -q --junitxml=data/local-checks/m1plus-regression.xml
```

`normalize_catalog.py` 只读取已有证据，不调用 xParse，也不自动审核或发布。相同 ID/版本重复导入幂等；内容变化必须使用新版本。每次标准化的成功/失败报告保存在 `data/normalized/m1plus/reports/`，最新结果位于 `extraction-report.json`。

- [M1+ 验收报告](docs/m1-enhancement-report.md)：逐文件变更、真实字段与来源哈希、测试、边界和 M2 接口。
- [目录服务](backend/ruleforge/catalog/service.py)：`create_candidate / validate_candidate / review_candidate / publish_record / get_record / list_records`。
- [v2 迁移](backend/ruleforge/persistence/migration_v2.sql)：保留全部 v1 表及已有数据。
