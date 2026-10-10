# 第二章第三次部署前冻结基线

本报告记录旧反馈流程结束于供应商故障时的真实状态，不是最终讲义验收。未改原稿、生产源码、任务数据库或讲义，没有新增 API 调用、编译或逐页视觉审查。机器证据为同目录 `CH02-pre-thirddeploy-baseline.json`；正文及检查点完整快照为 `CH02-feedback-tracking/snapshot-20260920-182420-770058.json`，SHA256 `f7fcdca6216cd5485458a1e37fdd3211a401b024889cdac49c1c20677336d31c`。

## 状态与产物身份

run `fd6736af6ef14be3839e019e86ca1e5c`，job `4678ed20f5c44ad89b289ffcee4d8143`，批准 revision 2。2026-09-20 18:23:12 UTC 停在 **FAILED / math.global_interfaces / 101 请求**，不是 AWAITING_USER_REVIEW。五节当前恢复候选均为 CHECKED，并与最新 checkpoint 一致，rowid 顺序为 37、41、47、48、50；全局累计修复轮次为 2，没有因失败清零。

当前数据库没有非 superseded 的正式 lecture.pdf。原 61 请求、17 页 PDF 仍保留但标记 superseded：artifact `12e006216ce3467ba012627c3e433721`，SHA256 `694d3b6783a984a65164ff3217fd19037c0333a25dac8603e70850b201115382`；配套原 TeX SHA256 `0eeff02f2258d9b398ff7a1a8c7a63316cab863c955f6f8ad97fd7bf61431496`。不能把这份旧 PDF 当作本次反馈后的输出。

最新 S05 累计编译已有 18 页，包含当前五节全部 82 个单元（逐一核对 tex 正文在源码中）。这是产品执行的实际 Windows XeLaTeX 两遍编译 PASS，无 compile issues；尚未完成全章复核和最终交付登记。

- 累计 PDF：`workspace/iteration2-live/b/fd6736af6ef14be3/sS05_968b477fdf4d/compile-attempt-1/build/lecture.pdf`，SHA256 `a8c9e95bb228d12569b0742f25e0c3a47d323a8234ec6d2a6796734eb96f31f7`。
- 累计 TeX：相邻 `compile-attempt-1/source/lecture.tex`，SHA256 `c82ad996aae2dce4c93bd8940480b974f7198dae4ccee5be3a0dfe1fa984e03a`。
- compile.json SHA256 `56655e82a3aefbad25ee3f374331a7a990e4ae06bc647d2f435b90cf936df09a`，两遍 stdout/TeX 日志由 checkpoint 的 compile_attempts 保存并绑定哈希。

## 实际反馈落实与修改性质

相较 61 请求基线，仅以下四个正文单元变化；对应完整前后文和候选 SHA 已在 JSON 保存。

| 单元 | 实际变化 | 独立判断 |
| --- | --- | --- |
| S02.U10 | 将有效的两收敛级数线性组合反证展开为有限部分和 B_n=C_n−A_n | 新文正确，但原证明也正确。是模型语义误报后的澄清，不统计为真实数学错误修复。 |
| S03.U14 | 在原直接比较答案中增补极限比较：与 1/n² 比值趋于 3 | 正项、参照级数及有限正极限均正确，落实反馈 F2，保留原正确路线。 |
| S04.U03 | 偶数部分和上界单列 m=1，再把含末项指标的展开限定 m≥2 | 明确最小指标与空项约定，无新假设或结论变化。 |
| S05.U18 | “以下答案与本节三道练习依次对应。”改为“本节三道练习，答案见讲义末尾答案区。” | 消除了将整个答案区开头误指为第五节三题依次答案的确定矛盾，落实 F1 的核心导航问题。最终 PDF 回链仍待新版本核查。 |

S03 新增核算曾错误地把 AST 写成 3n+1，产品 SymPy 正确返回无穷并阻断；随后只修核算 AST 为 `(3+1/n)/(1+2/n³)`，expected 保持 3，新正文没有被错误回滚，最后实际核算 PASS。该过程中错误候选、工具输出及局部修复均保留。

S05 导航首次被全章 reviewer 列为 warning 而未修；第二轮全章后实际进入 scoped 修复。最初新文又泄漏内部单元 ID，确定性 INTERNAL_UNIT_ID_VISIBLE 检查阻断，局部 patch 仅修改 U18，得到上述自然语言导航。当前候选 SHA256 `8fb78f817e93c2b6ca85d97b94a7281e0e7ea7a12d24e29c2fb586f4988aba03`；最后本地 review、数学检查和累计编译已接受。内部 ID 曾生成不等于最终学生正文仍含该错误。

仍保留的小标题“本节练习参考答案（讲义末尾）”可以有更自然的导航写法，但正文已明确指向末尾；不能因为可选措辞就继续无限修补。最终审计应检查题答链接和实际排列，不能仅由行数字数宣布效果通过。

## API 失败证据与恢复边界

最后 call_id `8001f4303d17427bb7bdfce6fbec7c84`，gpt6，HTTP 200，elapsed 14.671 秒，`received_content_chars=0`、`stream_complete=false`、`finish_reason=null`，错误 `PROVIDER_RESPONSE`，消息“供应商流式响应结构错误或空正文”。event 1894 保存失败结果，1895 保存任务失败。未达到数学 JSON schema 校验；当前分类没有继续 fallback。无原始 SSE 完整归档，因此不能断言具体是哪种坏事件结构。

紧邻之前 gpt6 的 HTTP 504 在 event 1886 正确触发 event 1887 fallback，deepseek-flash 于 event 1890 成功。故这次不是“所有三个模型均不可用”，也不是数学错误或预算耗尽；是空/异常流响应分类未进入已有容错路由的已观察缺口。

失败诊断 artifact `c52697f1e5574c2ba3993318bbb8a289`，`runs/fd6736af6ef14be3839e019e86ca1e5c/errors/d70c708c787e.json`，SHA256 `fb446405d24d64aa9255b55fc3434cac982f04fbf15493b2898a579e08b3e6d6`。父任务已决定修复分类并保存状态恢复；本审计没有点击重试或追加请求。

新协议部署后的全章复检、最终 PDF 逐页 agent 审读和 16 项原稿对照仍待执行。教师数学/视觉验收均 NOT_RUN。本次审计快照首次写入遇 workspace 权限失败，随后相同只读脚本获授权后成功；没有以权限失败掩盖产品检查结果。
