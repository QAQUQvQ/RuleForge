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
角色约束、字面关键词检索、装备、可注入骰子、攻击、暴击与分项伤害。当前实际结果见文末 M2 验证记录。
## M3
状态机、反应插入、轮次/持续效果、命令幂等、版本冲突、事务回滚、事件重放；三种完整遭遇。
## M4
Homebrew 不可信输入、审核/发布、规则集隔离、版本冲突与受限模板安全。
## 发布
规则覆盖清单逐项验收；实际来源链接完整；回归报告、部署说明与演示材料。

## M1+ 真实目录测试

`backend/tests/test_catalog.py` 验证分型 Schema、骰子和规则集边界、跨来源引用、HTML 网格、真实 JSON Pointer/哈希、候选审核发布、篡改拒绝、重复导入、SQLite v1 无损升级及失败回滚。

完整命令：`.venv\Scripts\python.exe -m pytest -q --junitxml=data/local-checks/m1plus-regression.xml`。测试使用已有真实产物，不触发解析服务。最终数量与结果见 [M1+ 验收报告](m1-enhancement-report.md) 和 JUnit XML。

## M2 验证记录（2026-10-13）

开发前重新运行完整套件：133 passed、0 skipped、1 warning，终端耗时133.54秒；[基线JUnit](../data/local-checks/m2-before.xml)。不是引用历史数字。

`test_m2.py` 增加89项测试：属性边界与熟练、AC固定向量及已授权适配器、骰子解析/预算/固定序列、自然1/20和优势劣势、Finesse/非熟练/投掷射程、分项伤害/暴击/防御、临时HP与零HP信息、角色CRUD/回滚/CAS、检索权限和登记别名、运行时各绑定篡改/撤销、v2→v3与迁移失败回滚、端到端重复输出。

M1/M1+ 的133项继续保留。原迁移测试只把最新数据库期望从2调整为3，把“未来版本”样本从3调整为4，保留逐表无损与失败回滚断言；没有放松证据校验。

最终完整执行：**222 passed，0 failed，0 errors，0 skipped，1 warning，443.69秒**，由 [m2-regression.xml](../data/local-checks/m2-regression.xml) 与 [M2 实施报告](m2-implementation-report.md) 记录。前端 `pnpm --dir frontend run build` 已通过 tsc 与 Vite7.3.7。Schema 导出使用真实 Pydantic 模型。

中间开发运行如实保留：一次86项新测试运行出现3项代码哈希失效（运行中修改了适配器文件）；另一次完整运行221 passed / 1 failed，原因为测试可变字典污染了期望值，已改为独立深拷贝。正式实现不会绕过哈希失效；最终验证重新准备隔离许可。

真实证据测试读取既有PDF/JSON，模拟审核仅在`m2-demo*.sqlite3`或pytest临时目录发生。`scripts/demo_m2.py`拒绝正式数据库路径，不删除数据库、不调用解析服务。完整演示结果保存在 [m2-demo-result.json](../data/local-checks/m2-demo-result.json)。

浏览器验证使用隔离数据库与构建后的前端，通过页面操作检查检索、来源详情、创建、装备AC和固定骰子结算。临时静态检查服务在Windows上显式设置JavaScript MIME类型；日常开发仍使用既有Vite服务，不修改系统MIME配置。
