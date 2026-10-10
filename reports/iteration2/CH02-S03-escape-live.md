# CH02 S03 新转义反馈的真实运行核验

观察结论：新诊断反馈确实进入真实请求，第一次 schema 纠错随后返回合法 S03 writer 候选。后续局部数学修复与编译也已形成 S03 CHECKED checkpoint。此结论是一次真实观察，不代表改进必然成功，也不是教师验收。

任务 `fd6736af6ef14be3839e019e86ca1e5c`，执行快照为 `live_retry3_ch02_source_snapshot.json`；新进程 provider SHA 与补丁源码一致。此诊断仅使用 SQLite `mode=ro` 和文件只读访问，没有创建 Pipeline/Worker/Service，没有追加 API 调用或写真实状态。

## 实际链条

- 请求 **20**：S03 writer 初次完整响应（HTTP 200、SSE complete、stop），90.313 秒；仍为非法 JSON。归档 `invalid-a34d136816924fb797d8acc8a5ee4e81.txt` SHA 为 `b9129a7ef260b092d9aca9358303eac273f6d010c4b0151ed3cb911a9b96a0ba`。
- 事件 **712**：真实记录 `json_escape_diagnostic.protocol_version=1`、两处非法转义、完整扫描 6898 字符、未截断。对归档重算的诊断 SHA 与事件完全一致。
- 请求 **21**：带新诊断反馈的第一次 schema 纠错。利用锁定计划、原 S01/S02 checkpoint、受限参考样例、schema 和匹配源码重建完整 messages，得到 input hash `4c33276a1c0e0887b95d269922502e560971a239e7682cc0b1b2a5fee6e82675`，与真实 provider.request 事件逐字一致。因此反馈“已发送”的判断有输入 hash 证据，未仅凭代码存在推断。
- 请求 20 的原始 messages 同样重建为 `3e7379500e8bc2613621a7a0986e5dad344e03c0328ba5a093d1fe240d5f7236`，与本次及先前 retry2 原始请求一致。两次请求的完整响应记录均关联各自相同 input hash。
- 请求 21 结果通过严格 JSON + WrittenSection schema，记录 `schema_attempt=2`。实际候选位于 `b/fd6736af6ef14be3/sS03_4728b49f0563/candidate.json`，16 个单元、2 个核算请求；字节 SHA `76cd55592c13e333784411f7ed1d3521debae19b78989b613ffd850292a5cd66` 与 writer cache 指针一致，严格验证后的对象 hash `ebdfc86d801277480a98634c72a99248da531e95830f1575ee30f4df4b050427` 与 provider 成功事件一致。

此后请求是数学审阅、严格局部补丁和再次审阅，不能把它们误记成 writer 的第二、第三次 JSON 修复。最终 S03 local state 为 CHECKED，只有 U12 接受一次局部修改；checkpoint 显示实际数学核算 PASS、Windows compile PASS。原 writer cache 仍标 unchecked，与“writer 原稿不是经过检查的最终稿”的语义一致，最终有效性来自独立 checkpoint。

## 累计次数与保留证据

本次恢复前累计 19 次；保存本报告快照时累计 **26/60**，provider.request 事件数与数据库累计一致，任务已经进入 `write.section.S04`。没有把旧 19 次清零，也没有调整 60/240 的预算。

S01 checkpoint hash `fc5da81980d11630e73c1c358e0c98a902cbc6de4199bd3dff87a427dbc98e79`、S02 `2af2bc64cd5bb2e928c25d521f62f94ffc0d4656e64acec1b2735a13f111a43c` 均与 retry2 诊断时一致，对应源码字节 SHA 也均匹配。旧非法回复没有被修改或当作合法候选采纳。

完整请求职责映射、响应耗时/usage、原归档与诊断 SHA、合法候选链和当前状态见同名 JSON。并非抓包：messages 是从已知只读输入与匹配源码重建后，与真实记录的完整输入 hash 对照。

**局限：**这是一次“新反馈发送后得到合法 schema”的观察，不能隔离模型随机性或证明因果关系；未对非法回复宽松解码，也未声称合法新稿与非法原文数学内容完全相同。整个 CH02 尚未最终验收，教师视觉/教学验收 **NOT_RUN**。本子任务新增 API 调用为 **0**。
