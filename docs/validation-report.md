# M1 验证报告
验证日期：2026-10-12（Asia/Shanghai）。

## 真实解析
官方 xparse-cli 2.5.0，--api free；没有调用付费解析或大模型 API。
完整官方 SRD 5.1：403 页；code=200；success_count=403；403 个页面均为 Success；14,164 个元素。
原始响应保留在 data/runs/srd51-full-001/raw/SRD_CC_v5.1.json。
原始 CLI stdout/stderr 均为空且保留。退出码 0 经执行工具实际返回；不是推测。
源 PDF SHA-256 和 JSON SHA-256 位于 manifest.json。
服务返回 duration_ms=75250；manifest 的 finished_at 是本地登记完成时间，不等同于服务处理耗时。
首次命令使用技能要求的私有任务上下文，Windows ACL 仅允许当前用户访问，随后已删除。
本地技能及参考文档保留于 docs/vendor/xparse-parse；本机使用项目依赖安装，不修改全局技能目录。

## 规则
srd51.ac.leather v1：AC = 11 + floor((DEX-10)/2)。
三处独立证据：PDF 64 页 Leather 护甲表、63 页轻甲说明、76 页调整值说明。
DEX=14 -> AC=13；DEX=9 -> AC=10；六个发布金标准覆盖 1/9/10/15/20/30。
无甲、非皮甲、盾牌、替代公式拒绝；不自动结算法术、掩护或其他战斗修正。
验证方式：原文与表格严格匹配、来源完整性检查、数值测试。human_review=false；不冒充 DM 人工审核。

## 自动验证结果
最终 pytest：47 passed，0 skipped；1 条 Starlette/httpx 测试客户端弃用提示，不影响通过。
机器报告：data/test-results.xml。
包括恶意 DSL、严格类型、深度限制、未支持情况、伪成功拒绝、事务回滚、真实 API、发布幂等，以及 PDF/JSON/清单/数据库来源/DSL/审核状态篡改拒绝。
TypeScript：tsc --noEmit 通过。
Vite：生产构建通过；标准 pnpm --dir frontend run build 也已实际通过。
浏览器视觉验收未执行；前端仅为最小验证界面。

## 范围
完整 PDF 已解析；只有一条规则被结构化并允许计算。
其余 SRD 内容保留在真实原始 JSON；不是已支持的可执行规则库。
角色、战斗、命令和事件已提供 Schema；未实现人物创建流程、战斗状态机、Homebrew 上传/审核。
没有自动启动常驻服务或进行公网部署。
