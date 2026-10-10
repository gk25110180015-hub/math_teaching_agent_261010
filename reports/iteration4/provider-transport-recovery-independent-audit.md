# 空响应与流协议恢复候选独立审查

结论：最后收窄版本未发现阻止部署的问题。可以随逐项反馈候选一起按 manifest 部署，然后运行完整本地回归及真实任务恢复。本报告仅补充传输差异，保留先前 `feedback-assessment-independent-audit.md` 及其 SHA 原文不变。

冻结 provider 候选为 `provider-transport-recovery.candidate.py`，SHA256 `7ffd9ac5783bf062b5c62aaa364a846180c1bb2a567280a347a97bdf39dfa944`；routing 候选为 `model-routing-transport-recovery.candidate.py`，SHA256 `a8040a14f659112920d4ea9848e3e38839c17d316a6ca4117ef2aec7f551dffe`。独立计算 SHA 与清单相符，两个 Python 文件 AST 解析通过。provider 包含先前逐项反馈 role 单次结构响应改动；原 a291 版本仍保留，不覆盖其历史测试证据。

审阅了实际窄 diff、完整相关解析/路由分支和新增测试断言：

- 合法停止但没有正文，或非流式正常 envelope 没有正文，分类为 PROVIDER_EMPTY_RESPONSE；SSE 不完整、坏事件、缺终止或终止后追加正文，分类为 PROVIDER_STREAM_PROTOCOL。它们进入现有 gpt6→deepseek-flash→deepseek-v4-pro 的有限路由，不发布部分正文，不修改用户选定的模型偏好。
- refusal、content_filter、显式 length、业务错误 envelope、tool_calls 等未支持完成类型保持非自动切换。原先 HTTP 400/422、权限/取消/租约/预算与已完成业务 schema 的行为未被泛化修改。
- 初审发现非 SSE Content-Type 直接进入协议 fallback，可能绕过普通 JSON 中的明确拒绝。最终候选已改为保守保留 PROVIDER_RESPONSE，不在未读正文时推断可切换。新增六种普通 JSON 响应（空、error、refusal、content_filter、length、完整有效正文）负测均断言只有一次调用且没有 fallback。
- 完整数学响应中存在 blocking issue 时正常返回该 issue；完整非空数学 JSON 的 schema 错误仍为 INVALID_MODEL_JSON，不转用备用模型获得不同判断。此次不以 fallback 洗去有效疑点。
- 原始 SSE 不归档推理内容；保存实际读取字节数与 SHA、收到正文字符数、完成状态、响应 ID、计费不确定性及每次路由事件。错误响应不能被冒称已消费的完整评估。逐项反馈的同槽 pending 恢复识别新传输码，完成后无效/未决裁定仍阻断。

验证证据：`feedback-receipts-validation/20260920-183027-64c540/pytest.log` 与 JUnit 独立读取，**117 PASS、0 fail/error/skip，4.27 秒**。覆盖传输恢复、旧流解析、模型路由、逐项反馈持久恢复、供应商失败证据和 prompt 身份。context 内既有 API/UI 清单保留旧联合历史，因此另独立核对实际隔离包 `workspace/t/fbr-64c540/src/math_agent/` 的 provider/routing 字节：确实是本报告两个最终 SHA，而不是旧 provider。先前 118 项逐项反馈测试是真实历史，与本 117 项有重叠，不能相加称总数或冒称全量回归。

真实触发证据来自 CH02 的第 101 次调用：HTTP 200、正文字符数 0、流未完成、finish_reason 空，旧解析层给 PROVIDER_RESPONSE 后直接失败。原事件没有 raw SSE，因此无法还原具体坏事件，不能声称这次真实故障已由 mock 完整重放。新逻辑覆盖有界、可复现的空正文/SSE 协议问题；若实际供应商返回非 SSE 格式，则按最后保守边界仍阻断并保留证据。

本独审新增真实 API 调用 **0**，没有改生产源码、数据库或讲义。部署后全量回归、实际 API 恢复、Windows 编译和 Edge 在本报告时 **NOT_RUN**；教师数学/视觉验收 **NOT_RUN**。下一步须真实恢复保留的任务，并分别记录传输恢复与教学反馈落地结果。
