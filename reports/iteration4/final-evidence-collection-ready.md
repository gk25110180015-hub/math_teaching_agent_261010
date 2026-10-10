# 最终只读证据采集入口

脚本：`collect_final_live_evidence.py`。**已准备，最终采集尚未执行**。仅做过 `--help`、Python 语法及合成事件分类验证，结果 PASS；证据为 `final-evidence-script-validation-20260920-160404-9725f0.json`。

待两章达到稳定状态后，在工程根目录运行：

```powershell
.\.venv\Scripts\python.exe reports/iteration4/collect_final_live_evidence.py --case CH02 --case CH03
```

默认读取 `http://127.0.0.1:8766` 的正式 GET 接口，以及 `workspace/iteration2-live/agent.db` 的短只读一致性事务。会话 Cookie 仅留在内存，不写入报告。输出新建到 `reports/iteration4/final-live-evidence/<UTC时间戳>-<随机后缀>`，不覆盖旧报告、原始资料或 benchmark manifest；不实例化会修改状态的 Service/BenchmarkRunner。

每章结果包括原审批整行、输入与计划内容/哈希核对，首次增额报告的完整旧事件前缀，原 33/27 次请求及当前全量请求账本，版本连续的预算动作与反馈动作，全部 current/superseded 产物的实际文件 SHA，以及人审表/事件是否仍为空。请求指标直接复用 `benchmark.request_metrics`。

归属检查候选新增的 `review.evidence_attribution` 事件也会完整保存并按原值统计各阶段；通过 evidence_key 只读检查该任务的 `review-attribution/<identity>/state.json` 及 dependencies 文件 SHA，输出 `attribution-evidence.json`。`attribution_error_summary` 按 `job.finished` 事件计数当前 `REVIEW_EVIDENCE_BLOCKED`、历史 `REVIEW_EVIDENCE_UNRESOLVED` 和 `REVIEW_EVIDENCE_CACHE_INVALID`，不重复计算 run/job 快照中同一错误。`BUDGET_EXHAUSTED` 原样独立统计，可能来自其他阶段，不自动算作归属失败。状态及事件中的 `TRANSPORT_PENDING`、`UNRESOLVED` 或历史 `UNSOLVED` 等原值均保留，不因错误码更名而改写。RESOLVED 只代表该自动归属流程的状态，不能算教师审批。该扩展的实际新 guard 产物最终采集尚未执行；运行中的文件可能在 SQLite 快照之后变化，文件另记读取时间。

逐项反馈新增完整归档：`feedback-receipts.json` 保存所有 `feedback.reviewed` 回执，`feedback-evidence/<identity>/` 保存各自 immutable 输入、模型响应、回执、失败与其他依赖的原始字节，并核对 SHA 和 state 身份。受审正文来源是该回执的 `input.json`，核对其 context hash、原始反馈 hash、批准 plan/hash/revision 及 checks.rerun_requested 的 sequence/payload hash；不会把第一次反馈响应直接当作最终结果。纯校验函数可重放保存响应的结构、逐字证据和范围约束，不发起模型请求、不更改 helper。

当前结果写入 `feedback-current-delivery.json`：只选择最新 build job（时间相同用 rowid）、当前批准计划、最新非空反馈动作之后的最后一条对应回执；最新回执损坏时不回退旧 PASS，新空反馈撤回旧结果。用 current source_map 的顺序在内存重建该受审正文，再由现有纯 render_lecture 输出 TeX，并逐字节 SHA 对照唯一当前 lecture.tex。记录受审 units 整体及逐单元 SHA、当前交付 TeX SHA、重渲染 SHA 和对应 job/事件/身份；历史正文与最终正文不同会明确标记。

归档完整性 PASS、当前反馈正文对应关系和最终交付快照可用性分开记录。`final_delivery_snapshot_ready` 只有在两章无活动任务且 AWAITING_USER_REVIEW、最新回执与最终 TeX 一致、没有未决/待改进项、正式 API 展示的回执与 DB 快照对应时才为 true。运行中最近一次回执只能描述当时快照，不能表示新 patch 已被复评。全部 job.finished 错误码按原值计数，包括后续传输分类及 FEEDBACK_REVIEW_BLOCKED/FEEDBACK_EVIDENCE_BLOCKED，不据 HTTP 200 断言成功。

脚本扩展已通过 10 项隔离合成验证（新旧正文、最新选择、空反馈、新 job、坏 JSON、pending、交付 SHA 改动和回执损坏），证据 `feedback-collector-validation/20260920-182812-55f8bb/result.json`。未读取生产 DB，未调用真实 API，未编译，未提交教师审核；正式最终采集仍为 NOT_RUN。验证使用原测试 helper 候选 021ca341…，没有修改其字节。

汇总仅把 `SCHEMA_VALIDATED` 计为有效返回；仅 HTTP 200 响应头为“完成未确定”，HTTP 200 后总超时仍为“已记录失败”。保留独立 billing_uncertain 与 usage 完整性，不推算未知费用为零。有效返回不等于数学内容正确。

总报告的 PASS 仅代表历史保留及文件完整性；是否处于 `AWAITING_USER_REVIEW` 且无活动任务由独立 `stable_delivery_snapshot` 字段记录。真实工作仍活跃时可以读取快照，但不能将该时点快照宣称为最终交付。Windows 干净源码编译、真实 UI 下载与教师视觉验收仍按各自流程执行。
