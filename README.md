# RuleForge V1.0 · 第一阶段
React + TypeScript / FastAPI / Pydantic / SQLite / pytest。当前只完成真实解析与单条可执行规则闭环，复杂人物创建、战斗执行和 Homebrew 导入尚未实现。

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
pnpm --dir frontend run dev
```
打开终端给出的本地 Vite 地址（通常 http://127.0.0.1:5173）。开发代理将 /api 发往 8000。

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
- docs/architecture.md：最终模块和信任边界
- docs/schemas/：Pydantic 导出的 Rule / Character / Creature / Item / CombatState / Command / Event JSON Schema
- backend/ruleforge/persistence/schema.sql：实际数据库定义
- docs/rule-dsl.md：已支持 DSL
- docs/testing.md：分阶段测试计划
- docs/rule-coverage.md：覆盖范围
- ATTRIBUTION.md：SRD 署名与派生内容说明

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
