# 恢复时证据采集器复核

2026-09-22 UTC。暂停前已完成全局迁移及数学疑点台账的只读归档扩展，本次检查未改写采集器、生产源码、测试或真实数据库，也未发起模型调用。

| 文件 | 本次读取的 SHA256 |
|---|---|
| collect_final_live_evidence.py | f1b2d42041f2054a4ec8bb8bada358faa17e229f54c63c8da5b21c97cf5f6e47 |
| recovery_evidence_archive.py | 059c8263aa75813cd1658485f5d4fe52ccd2690ee7865679eec61ef5fedb9748 |
| uncertainty_review.candidate.py | 288a374421c952020165b4ec12585e98e4dc5948dacad3d49df759e342f632e2 |
| global_repair_contract.candidate.py | 8c1167ba608adbc1b74d9fe4d5852152eba74069606c466a4c2db606c8df2186 |

原采集器保存在 `collector-history/before-recovery-20260920-192828-05f1a4/`，SHA256 为 `8dac19db0bb75f398ef50291378f48aa51970904f7266f5b60a1b19163680023`。备份 manifest 存在且与原字节相符。

已核对新候选的事件名、事件字段和台账路径。全局迁移归档记录原状态、迁移后状态、当前状态、计划及审批身份、保留请求数和轮数、待修范围，以及各节候选文件的原始字节与 SHA。数学疑点归档记录所有事件与最后对应台账、声明原文、输入正文和逐单元 SHA、所有依赖原始字节，并调用纯验证函数重放保存的响应；不发起新裁定。

已有两组合成正负检查位于 `recovery-collector-validation/20260920-193401-f127b6/result.json`，状态 PASS，所记采集器、归档 helper 和疑点 helper SHA 与本次一致，因此未无意义重复执行。正例检查迁移归档和疑点响应重放；负例修改候选与响应字节后均被拒绝。该记录还用 AST 对照确认原 `feedback_final_ready` 与 `service_feedback_matches` 条件未改。它是合成文件完整性测试，真实 API、Windows 编译、浏览器、真实数据库及教师验收均未执行。

最终采集仍待真实任务稳定后执行。`resolved_by_current_body` 仅是对应正文的自动裁定，不是形式证明或教师审核；疑点台账本身不推断最终交付正文相同。最终可交付标志仍要求当前 job/计划/反馈动作一致、回执正文重新渲染的 TeX SHA 等于当前交付、没有待改进项、正式 API 投影一致、任务处于待用户审阅且没有活动 job。文件归档完整性不能代替上述判定。

V4 部署后完整 Edge 验收已另行启动，输出目录 `final-deployed-e2e/20260922-043328-aa8704/`。本报告写入时测试仍在运行，不能标记通过；以该目录最终 `result.json` 为准。
