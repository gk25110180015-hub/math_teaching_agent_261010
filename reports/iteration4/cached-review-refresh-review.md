# 已检查章节缓存契约修复候选

本子任务没有改动生产 `src`、提示词、真实任务数据库或 API 配置；没有发起真实模型请求。新增专项使用独立 SQLite、模拟模型和模拟编译器；相关回归集合另含 3 项实际 Windows XeLaTeX 测试。

## 交付

- `cached-review-refresh.patch`：只修改 `src/math_agent/pipeline.py`，应在真实 Worker 停稳后由主任务合并。
- `cached-review-refresh.candidate.py`：与补丁对应的完整候选源码，供审查及隔离解释器加载。
- `../../tests/test_cached_review_refresh.py`：14 项行为回归，已经写入测试目录。
- `prepare_cached_review_patch.py`：根据未改动的生产基线生成补丁，不写生产源码。
- `verify_cached_review_candidate.py`：仅在独立测试解释器中加载候选类，不写生产源码。

基线及验证后生产 `pipeline.py` SHA256 均为 `350f9eff0d4a8f24937e4c0dfc605f7f2bb928fc603b313d99219553ea628a1c`。

## 具体行为

1. 新 checkpoint 保存审批计划、章节规格、模型/提供方身份，以及检查契约。契约包括数学检查器、独立 `series_domain_text.py`、规范化、引用、解析、编译、流水线、计算协议、LocalRecovery、数学审阅提示词、输入/审阅 schema、相关库版本和编译设置。独立定义域检查器未部署时记录 `MISSING`；部署或缺失会改变契约。
2. 相同输入和相同检查契约才能直接复用既有检查报告。旧 checkpoint 没有契约，或检查代码/提示词、上游正文发生变化时，保留原稿，以最新合法已接受内容为未检查种子，重新规范化、检查、审阅和编译，不重调 writer。
3. 在任何旧章节被新 checkpoint 替换前，按当前批准计划/规格和完整旧正文前缀逐节重算旧输入哈希，核对 checkpoint 输出、源文件 SHA 与受控路径。把已验证旧前缀以 SHA 命名的文件持久保存，并在有有效 worker fencing token 的事务中登记证据事件。
4. 上游修正文并提交新 checkpoint、下游随后失败时，下一次恢复仍能重用正确稿件：新 checkpoint 根据显式审批身份读取为未检查种子；legacy checkpoint 必须匹配持久证明内的输入/输出 SHA，并重新验证完整历史前缀和源文件，不能只凭 section ID 认定同一计划。
5. 若 LocalRecovery 已接受的稿件比 checkpoint 更新，先校验其身份、路径和 SHA，随后由 LocalRecovery 再核验全部依赖证据。以该新稿继续检查，保留原审批、计数、未决问题和历史。全局 `forced_sections` 仍优先。
6. checkpoint、源文件或持久前缀证明损坏时阻断并保留证据，不借重新写作绕过。不同审批计划不继承旧计划的稿件或 PASS。

## 已执行验证

| 检查 | 结果 | 证据 |
|---|---|---|
| 原生产代码的初始回归 | 7 FAIL / 2 PASS，证实缺陷 | `cached-review-refresh-red.log`、`.xml` |
| 初版候选相关恢复回归 | 75 PASS | `cached-review-refresh-candidate.log`、`.xml` |
| 初版候选跨重启补充回归 | 3 FAIL / 10 PASS，暴露旧前缀丢失问题 | `cached-review-refresh-restart-red.log`、`.xml` |
| 补充持久前缀证明后的相关回归 | 79 PASS，38.37 秒 | `cached-review-refresh-candidate-02.log`、`.xml` |
| 最终候选专项，含独立定义域检查器版本变化 | 14 PASS，4.31 秒 | `cached-review-refresh-candidate-final.log`、`.xml` |

测试数量有重叠，不能相加。最后一步仅加入独立定义域检查器 SHA，并增加该文件单独变化导致重检的行为用例。最终产品与其他子任务修改合并后的完整回归由主任务执行。

真实 API 测试：NOT_RUN。相关集合中的 3 项实际 Windows XeLaTeX 测试通过，其余编译为 mock。人工数学及视觉验收：NOT_RUN。原失败记录和隔离测试数据库均保留。

后续独立审计发现了真实 steps 多版本排序与未 checkpoint 连续恢复边界，已在最终 `cached-teaching-quality-combined.patch` 修复。此早期单独补丁保留为历史证据；实际合并请采用 [最终候选说明](teaching-quality-candidate-review.md)。
