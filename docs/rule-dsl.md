# RuleForge DSL v1
当前发布范围刻意限制为 srd51.ac.leather v1。新增操作和模板必须修改显式白名单并增加来源及测试，不能通过字符串运行代码。
```json
{
  "dsl_version": "1",
  "id": "srd51.ac.leather",
  "version": 1,
  "ruleset": "srd-5.1",
  "category": "armor_class",
  "requires": [
    {"field": "armor", "op": "eq", "value": "leather"},
    {"field": "shield", "op": "eq", "value": false},
    {"field": "alternative_ac", "op": "eq", "value": false}
  ],
  "expression": {
    "op": "add",
    "args": [
      {"op": "const", "value": 11},
      {"op": "ability_modifier", "ability": "dexterity"}
    ]
  }
}
```
const 取整数 [-100,100]；add 2–8 个参数；AST 最大深度 8、节点数 64；只允许 dexterity 的调整值节点。
编译阶段解析 HTML 表格中的 Leather 行并严格核对 AC 列；轻甲和调整值原文必须唯一匹配。不会自动猜测 OCR 错别字。
执行前要求数据库 verified、DSL 与当前受审模板一致、验证哈希一致、原始证据及数据库来源一致。
Schema 的语法合法不等于允许发布；任意合法 AST 也不能直接经 API 执行。
条件和效果冲突在 M1 通过只支持一个模板拒绝。M2 扩展前必须定义互斥 AC 公式、可叠加加值与时机，不能将多种基础 AC 相加。
