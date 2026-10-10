# 自动复检入口提案

状态：**PROPOSED_NOT_APPLIED**。生产 Service、API、app.js、数据库和正在执行的真实任务未修改。

[automatic-recheck-fix.patch](automatic-recheck-fix.patch) 为三文件补丁，不需要数据库迁移。它增加 `POST /api/runs/{run_id}/recheck` 和“重新运行自动检查”按钮；请求复用 `ExecuteRequest`：`expected_plan_revision`、`expected_plan_hash`、`idempotency_key`。

只有 `AWAITING_USER_REVIEW` 且原计划/输入仍获确认、没有活动 job、历史请求预算已核验的任务可以创建复检。已取消或已发布任务拒绝该入口。同一动作键和相同请求重放返回原 job；键相同而请求不同报 `ACTION_CONFLICT`。创建动作与事件、旧产物历史化、新 build 入队在同一事务中完成。

此操作保留原审批、输入、累计预算、请求次数、局部修复状态和章节检查点；新 build 使用现有 Pipeline。哪些章节需要重新检查由另行实现的 `cached_review_refresh` 检查契约决定，本补丁本身不把旧缓存视为已经通过新版检查。预算不会自动增加，执行中的模型调用按既有规则记账。

原 artifacts 全部标记为 `superseded`，文件、哈希和原人工复核记录保留。历史文件仍走原下载端点，继续验证哈希。界面在“历史交付”折叠区提供下载；本次预览、逐页复核和报告审核只显示当前文件。

人工审核 API 拒绝 superseded 文件；发布所需页图、质量报告、未解决 issue、最终 accepted 更新和新人工审核收据都排除历史文件。自动复检不创建 `human.review` 事件，也不假造教师批准。新复检若失败，旧文件仍可在历史中下载，失败诊断及新候选按现有机制保留。

验证结果：

| 检查 | 结果 | 范围 |
|---|---|---|
| 原生产源码红测 | 12 FAIL / 1 PASS | 新入口尚不存在；CSRF 检查仍通过 |
| 提案隔离回归 | 66 PASS，3 个测试/依赖警告 | 新 13 项 + 旧 API 与预算回归 |
| JS 语法检查 | PASS | Node.js `--check` 读取提案文本 |
| 真实 API / Windows 编译 | NOT_RUN | 合成产物；mock Pipeline.build |
| 浏览器交互 / 教师验收 | NOT_RUN | 合入后由主任务执行真实 UI 检查 |

隔离回归使用真实 SQLite、Service、FastAPI 和 Worker。Worker 构建部分由合成产物替身替代，测试产物中的 PDF/PNG 是明确标注的占位字节，不是编译或视觉成功证据。复核按钮请求仅提交到测试临时数据库。隔离测试前后三份生产文件哈希一致。

证据：[红测日志](automatic-recheck-red.log)、[红测 JUnit](automatic-recheck-red.xml)、[隔离日志](automatic-recheck-proposed.log)、[隔离 JUnit](automatic-recheck-proposed.xml)、[JS 检查](automatic-recheck-javascript.log)、[文件哈希 manifest](automatic-recheck-manifest.json)。新增回归在 [test_automatic_recheck_api.py](../../tests/test_automatic_recheck_api.py)。

合入时先核对 manifest 中的原文件哈希；应用 diff 后直接运行这 13 项及旧 API/预算回归，再做真实浏览器“复检按钮→历史交付→当前复核目标”流程验收。此报告不代表提案已经部署。
