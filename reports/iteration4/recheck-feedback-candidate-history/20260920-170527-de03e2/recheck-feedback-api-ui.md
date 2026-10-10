# 自动复检反馈入口候选

状态：**PROPOSED_NOT_APPLIED**。未修改生产源码、运行中的真实任务或数据库。补丁为 `recheck-feedback-api-ui.patch`，包含 domain、Service、Web API、app.js 四处窄改动；每个原文件与候选文件的 SHA-256 见 `recheck-feedback-api-ui-manifest.json`。

`RecheckRequest` 继承 `ExecuteRequest`，新增 `feedback: str = ''`（最长 10000 字符）与 `feedback_source: Literal['user','agent_audit'] = 'user'`。仅 `/recheck` 接受这些字段；普通 `/execute` 保持原协议并拒绝额外字段。

`checks.rerun_requested` 事件在原有 `plan_hash`、`plan_revision`、`job_id`、`idempotency_key` 和 `payload_hash` 上增加原样反馈及来源。两个新字段参与幂等哈希；同键变更反馈或来源返回 409。对于升级前缺少这两个字段的旧事件，仅空反馈、默认 user 且原 ExecuteRequest 哈希匹配时允许回放，不改写历史事件。通过旧 ExecuteRequest 直接调用 Service 的无反馈调用也保留兼容。

仅允许原审批合法、无活动任务、等待人工复核的未发布任务创建新复检任务。反馈不改变原审批、计划、预算和累计计数，不直接编辑正文，也不提交教师审核。旧文件仍按已有规则标记 superseded，保留下载历史。Pipeline 候选通过匹配批准计划和当前 job 的最新事件，把反馈作为未核实观察交给整章审阅；对应补丁由另一代理准备为 `recheck-feedback-pipeline.patch`，本文件不包含该部分。

界面增加“本轮希望改进的内容（可选）”文本域，不要求内部 ID。草稿按 runId 保存在当前页面内存中，轮询或强制重渲染会还原输入；请求失败保留，成功提交才清除。整页刷新不持久保存未提交草稿，与本次最小实现范围一致。用户从界面提交的来源固定为 user。

验证：新增 18 项离线回归，旧生产 **12 FAIL / 6 PASS**；隔离加载候选后，加既有自动复检/API/预算回归共 **84 PASS，10.58 秒**。真实 SQLite/TestClient，mock 数据；4 个生产文件前后 SHA 不变。`node --check` **PASS**。

进一步联合验证：将这四个候选文件和 Pipeline 反馈候选装入同一个独立临时源码包，**46 PASS，7.33 秒**（API 新增 18、Pipeline 新增 13、正式 TestClient→新 job→Pipeline 集成 2、既有复检 13）。新增集成覆盖 user/agent_audit 两种来源，证明正式 API 写入的真实事件进入新任务的全章模型上下文，缺口触发既有限定单元修订，修复后的全文再次审阅，原审批/预算/计数/历史下载均保留，没有教师审核。生产 5 文件 SHA 不变。证据见 [联合候选结果](recheck-feedback-combined/20260920-155629-04727c/result.json)；独立源码与测试 DB 保存在 `workspace/t/fbpkg-04727c`。两组回归有重叠，不累加为独立案例总数。

新真实 Edge 测试 `tests/e2e/test_recheck_feedback.py` 已成功收集 1 项，**尚未执行**。待统一部署后验证：输入→实际轮询→强制重渲染→合成一次 HTTP 409→草稿保持→真正提交→新任务/事件绑定→成功后草稿清空，同时检查原审批/预算、人审零记录及实际 Windows 编译。失败场景只拦截独立浏览器请求，不改真实任务。可设置新的 `MATH_AGENT_E2E_EVIDENCE_ROOT` 后运行该文件，勿复用历史证据目录。

真实模型 API、Windows 编译、真实浏览器运行、教师数学/视觉验收：本候选阶段均 **NOT_RUN**，不能把早先其他版本的通过记录视为本候选验收。

证据：[红测](recheck-feedback-api-red.log)、[隔离候选回归](recheck-feedback-api-candidate.log)、[机器清单](recheck-feedback-api-ui-manifest.json)、[浏览器收集](recheck-feedback-browser-collection.log)。
