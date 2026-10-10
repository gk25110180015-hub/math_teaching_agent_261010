# 复检反馈进入全章审阅：Pipeline 窄候选

状态：**候选已通过隔离 mock 回归，尚未部署**。生产任务仍在运行，本候选没有写入 `src`、提示词、活跃数据库或章节成果，没有 API 调用。

## 合并身份

以下均为文件原始字节的 SHA-256，不是换行规范化哈希，也不混用补丁与完整候选：

| 文件 | raw SHA-256 |
|---|---|
| 生产基线 `src/math_agent/pipeline.py`；报告内保留 `recheck-feedback-pipeline.base.py` | `504e66ea5d2abaec818deafa3420ec70db82fbdee59638fed1c64e8383250fa8` |
| [完整候选](recheck-feedback-pipeline.candidate.py) | `43058915b1775a9236d0a98732aa8131c4f2eecddbdf09802a14d7ad14b34695` |
| [仅 Pipeline 差异补丁](recheck-feedback-pipeline.patch) | `08c8b2dd1ff87abceb4f36a1af2c06be73a132a984775f46c1f9c4e321fe8b9a` |
| 测试期间生产 `reviewer_math.md` | `cd75bbcf1516a0fa5ecaa882e753956e82d65da7e0640442db98717a1cf6f92d` |

[机器清单](recheck-feedback-pipeline-manifest.json)记录字节长度和独立 SHA。API/UI 配套候选由预算代理提供：[recheck-feedback-api-ui.patch](recheck-feedback-api-ui.patch)。须在真实任务停稳后统一合并，继续保留原失败日志和所有已接受候选。

## 行为与证据

`_recheck_feedback` 从实际 SQLite `events` 读取 `checks.rerun_requested`，按 `sequence DESC` 定位当前计划 `hash`、`revision` 的最新动作，并要求 `job_id` 等于当前 build。匹配计划的最新动作即使反馈为空，也不回退到早先反馈；其他计划不混入。`Service.retry` 在原 job 上执行 UPDATE，保留 job ID，实测失败重试能够继续同一反馈。

字段与 API 候选一致：`feedback`、`feedback_source`（`user` 或 `agent_audit`）、`plan_hash`、`plan_revision`、`job_id`、`idempotency_key`、`payload_hash`。旧动作没有反馈字段时仍按无反馈处理；保存后异常的类型、长度或来源会阻断，原事件保留。

反馈只进入 `chapter_coverage` 的模型上下文。上下文仍包含完整真实单元、批准目标及节—单元映射，并明确要求独立核查：反馈不是证明、教师验收或扩张范围的授权；已有正文已满足、与正文不符或超出审批范围的意见不能强行变成缺陷。问题必须指向现有实际单元。反馈不会改审批或生成 `human.review`。

每次到达全章检查时均重新审阅，合法 section cache 不跳过它。相邻接口若先有阻断，仍沿原流程先修复接口再进入全章检查，不把尚未运行的全章反馈审阅记作通过。确认的问题继续由既有 `issue_targets` / global / local 修复链处理，不直接改写交付文件。

在模型请求前保存 `chapter-coverage-<cycle>-feedback.json`：原动作全文、事件序号/时间/原 payload SHA、计划身份、实际受审单元 SHA、对应 review label、教师两项 NOT_RUN。随后原 `review_units` 逐次响应文件保持不变；最终全章报告增加反馈证据路径和 SHA。请求超时也保留已送审反馈及正文身份。

## 已执行验证

- [红测日志](recheck-feedback-red.log) / [JUnit](recheck-feedback-red.xml)：生产旧实现对 13 个新增测试均失败，符合尚无反馈接入的事实。
- [候选回归日志](recheck-feedback-candidate.log) / [JUnit](recheck-feedback-candidate.xml)：**77 PASS，25.83 秒**。13 个新增测试，加现有 teaching、cache refresh、global repair、global budget resume 和 global contract 回归。
- 新增测试用真实临时 SQLite；模型与编译器全部为 mock。覆盖缓存后反馈修复、user/agent 来源、原审批保留、最新空反馈撤回、旧计划隔离、跨 job 不继承、原 job 失败重试、请求失败前证据保存、虚构单元 ID 阻断和异常事件协议。
- 测试前后生产 Pipeline 与 V6 reviewer 原始 SHA 一致。
- **真实 API：NOT_RUN；真实 Windows XeLaTeX：NOT_RUN；PDF agent 视觉：NOT_RUN；教师数学/视觉：NOT_RUN。** Mock 只证明工作流接线与约束，不能证明模型将正确发现第三章覆盖缺口。

复现命令（工程根目录，使用新的 basetemp，避免复用既有证据）：

```powershell
.\.venv\Scripts\python.exe reports/iteration4/verify_recheck_feedback_pipeline.py tests/test_recheck_feedback_pipeline.py tests/test_teaching_quality_gate.py tests/test_global_repair.py tests/test_global_budget_resume.py tests/test_global_contract_guard.py tests/test_cached_review_refresh.py -q --basetemp workspace/t/feedback-candidate-new
```

CH03 审计准备和中间稿问题已另存 [快照报告](ch03-audit-preparation-20260920T154547210089Z/README.md)。未来通过正式 `/recheck` 提交范围内反馈，经真实审阅和修订后，再冻结成果审计 22 项 REQUIRED 与 G01–G08；不把当前候选部署等同于内容已修好。
