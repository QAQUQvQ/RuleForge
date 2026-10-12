import json, os
from pathlib import Path
p = Path(".tools/xparse-context.json")
p.write_text(json.dumps({"schema_version":"xparse_task_context.v1","user_intent":"开发 RuleForge V1.0：基于 TextIn xParse 和 D&D SRD 5.1 的规则检索、人物创建、完整战斗流程及 Homebrew 导入系统。\n技术栈：React + TypeScript、FastAPI、Pydantic、SQLite、pytest。\n第一阶段只实现：项目骨架、官方 SRD 5.1 PDF 真实解析、来源追溯、规则数据模型、至少一条经验证的可执行 AC 规则。\n请检查并使用 intsig-textin/xparse-skills；不允许模拟解析成功，不允许未经批准使用付费 API。保存真实原始解析结果、错误日志和来源信息。\n设计规则 DSL、角色/战斗状态 Schema、命令与事件模型，并制定测试方案。禁止执行大模型生成的任意代码，规则执行必须使用受限、验证通过的操作。\n先输出模块设计、项目目录、数据库 Schema、规则 DSL 草案和分阶段测试计划，再开始编码。不要一开始开发复杂前端。","tool_call_reason":"解析官方 SRD 5.1，保存真实证据并验证基础 AC 规则"}, ensure_ascii=False),encoding="utf-8")
os.chmod(p,0o600)
Path("data/setup").mkdir(parents=True,exist_ok=True)
