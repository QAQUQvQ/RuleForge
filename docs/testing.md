# 分阶段验证计划
## M1
- DSL 白名单、未知字段、深度/节点/数值上限；拒绝代码字符串、任意路径。
- AC 敏捷 1/9/10/15/20/30；护甲/盾/替代公式拒绝；仅已验证规则可执行。
- 来源文件、原始 JSON、quote 的哈希与 pointer 校验；破坏任意环节时拒绝。
- SQLite 外键、规则版本唯一性；API 就绪状态和来源返回。
- 真实证据测试必须使用实际 xParse 输出；缺失则 skip 并明确 M1 未通过。
- 异常测试的合成输入只能在单测临时目录，不得导入真实数据库或冒充解析成功。
- 前端 tsc 与 Vite build；真实 AC API 的手动/集成验收。
## M2
角色约束、全文检索、装备、可注入骰子、攻击、暴击与分项伤害。
## M3
状态机、反应插入、轮次/持续效果、命令幂等、版本冲突、事务回滚、事件重放；三种完整遭遇。
## M4
Homebrew 不可信输入、审核/发布、规则集隔离、版本冲突与受限模板安全。
## 发布
规则覆盖清单逐项验收；实际来源链接完整；回归报告、部署说明与演示材料。

## M1+ 真实目录测试

`backend/tests/test_catalog.py` 验证分型 Schema、骰子和规则集边界、跨来源引用、HTML 网格、真实 JSON Pointer/哈希、候选审核发布、篡改拒绝、重复导入、SQLite v1 无损升级及失败回滚。

完整命令：`.venv\Scripts\python.exe -m pytest -q --junitxml=data/local-checks/m1plus-regression.xml`。测试使用已有真实产物，不触发解析服务。最终数量与结果见 [M1+ 验收报告](m1-enhancement-report.md) 和 JUnit XML。
