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


## 2026-10-12 技能注册补充
已通过 Codex skill-installer 将官方 xparse-parse 安装到 C:/Users/23100/.codex/skills/xparse-parse。
固定提交：3662e0be9750cb57796a768015fc1e5fff29a793。安装记录：data/setup/skill-installation.json。
本次仅安装技能，没有新增解析请求或付费调用。原文关于“仅项目快照”的表述描述的是初次 M1 验证时的状态。
规则标准化与领域模型的具体边界见 docs/model-and-normalization-gaps.md。

## M1+ 最终回归（2026-10-12）

实际基线 47 passed；完成后完整回归 **133 passed，1 warning，0 failed / errors / skipped**，终端耗时 129.04 秒。新增 86 项覆盖五类记录、装备分型、来源完整性、目录生命周期和数据库迁移。

10 条真实 SRD 样本、42 个来源引用；全部 validated / review_required / reference_only。v1→v2 迁移及所有旧表内容保持、事务回滚与重复升级均经测试。完整重复导入无重复记录。皮甲规则和三来源仍可验证，DEX 9→AC 10、DEX 14→AC 13。未调用 xParse；未提交或推送 Git。

JUnit：[m1plus-regression.xml](../data/local-checks/m1plus-regression.xml)；详细结构、样本原文位置/哈希、逐文件变更与 M2 接口：[M1+ 验收报告](m1-enhancement-report.md)。
