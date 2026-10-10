# HTTP 200 空流/协议错误的恢复边界

真实 CH02 任务 fd6736af6ef14be3839e019e86ca1e5c 的第 101 次请求在 2026-09-20 18:23:12 UTC 失败。事件 1892–1895 记录 call_id=8001f4303d17427bb7bdfce6fbec7c84，首选 gpt6，HTTP 200，elapsed=14.671 秒，received_content_chars=0，finish_reason=null，stream_complete=false，错误 PROVIDER_RESPONSE。其后没有该请求的 fallback。上一独立请求的 HTTP 504 已正常切 Flash，说明遗漏是此错误类别。

源码表明本次在 `_read_sse` 的响应结构解析层失败，尚未到 MathReview schema 或数学意见校验。旧实现没有归档坏 SSE 原事件；现有记录不足以确定具体是 choices、delta、JSON 或其他结构错误，不能虚构供应商根因，也不能把“HTTP 200”当作成功数学输出。

最小候选在已冻结反馈 provider 上追加分类：

| 情况 | 分类/动作 |
| --- | --- |
| 有完成停止信号但无正文，或非流式合法信封正文为空 | PROVIDER_EMPTY_RESPONSE，可依已配置顺序切备用 |
| SSE 事件/信封无法解析、未收到完整 DONE/stop、停止后继续正文 | PROVIDER_STREAM_PROTOCOL，丢弃部分正文并可切备用 |
| 明确 refusal/content_filter、finish_reason=length | 保留原拒绝/截断，不切换洗掉结果 |
| tool_calls/不支持完成类型、SSE 显式 error 信封 | 保留 PROVIDER_RESPONSE，不推断业务错误可切换 |
| 请求 SSE 却得到其他 Content-Type | 保留 PROVIDER_RESPONSE，不绕过未读取信封可能含有的明确拒绝或长度说明 |
| 完整非空数学 JSON 的 schema/内容问题 | 原 schema 修复/阻断规则，不切换数学裁定 |

预算、取消、租约、首选顺序和单模型已有有限 HTTP 重试规则保持原样。三模型均空时分别保留失败记录并返回 PROVIDER_ALL_UNAVAILABLE，允许正式恢复；不会生成假 PASS。只增加安全字节计数、SHA 与固定协议错误类别，不记录推理内容或新增密钥落盘。

最终 provider 候选 SHA：7ffd9ac5783bf062b5c62aaa364a846180c1bb2a567280a347a97bdf39dfa944。routing SHA：a8040a14f659112920d4ea9848e3e38839c17d316a6ca4117ef2aec7f551dffe。

验证：最终隔离 mock **117/117 PASS，4.27 秒**，见 [日志](feedback-receipts-validation/20260920-183027-64c540/pytest.log)、[上下文及 SHA](feedback-receipts-validation/20260920-183027-64c540/context.json)。包括空 SSE→Flash、三模型皆空、usage-only 合法分块、推理内容不落日志、业务/math schema 不切、拒绝/截断优先、非 SSE 六种负对照、反馈同槽恢复。旧 112 PASS 版本的证据保留，不能替代最终 117 项。

本次没有调用真实 API，没有重试或修改真实任务，没有执行 Windows 编译/Edge/人工视觉验收。之前反馈候选的 118 项结果完整保存在旧清单，传输增量不冒称已经跑过部署后全量。

主 [feedback-assessment-manifest.json](feedback-assessment-manifest.json) 替换 provider 条目并追加 routing，原 provider 字节和 [旧 READY 清单](feedback-assessment-manifest-before-transport.json) 保留。最终需独审后 READY，再由父任务一次部署七文件。
