# 跨单元引文归属 guard：独立候选审查

审查结论：对下面固定 SHA 的候选，未发现会把已保存的未决裁定通过普通 retry 抽成 PASS、直接丢弃合法跨单元依赖批评，或将错引来源自动纳入正文修复范围的阻断问题。可以进入 root 的受控合并与部署后全回归。此结论是代码和恢复边界审查，不是模型准确率、生产验收或正式数学证明。

## 审查版本

候选尚未部署；[manifest](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/review-evidence-attribution-manifest.json) 的三个文件 SHA 已独立核对，两个 Python 文件均已实际通过 AST 语法解析：

|目标文件|候选 SHA-256|
|---|---|
|pipeline.py|`96d0f9e042836bf88fb1609159066d7b20113be41a193bbfa6e57f4f4086a683`|
|review_evidence_attribution.py|`078a3fe47159d8934b71b30df7d4940742a9b53ba2fbe0f3d0ab66b249377da5`|
|review_evidence_attribution.md|`0e2e9c9568299b12597b2a6637d5d043eb13f63c3e28702d8370b212958fc65b`|

此前较早版 helper `edd1a110...` / pipeline `ec82479c...` 的 69 项结果，以及 helper `62759e27...` 的 73 项结果，均保留且不能混用为最后版本的测试证据。最终候选实施者的隔离测试证据位于 [pytest.log](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/review-evidence-guard-tests-138950/pytest.log)、[JUnit](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/review-evidence-guard-tests-138950/junit.xml)、[测试 manifest](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/review-evidence-guard-tests-138950/manifest.json)：**74 mock 测试通过，18.33 秒，0 failure/error/skip，2 个已有依赖 deprecation warnings**。独审者读取了日志、新增测试代码并实际解析 JUnit 与测试 manifest，三文件 SHA 均与实际候选相同；没有另将此套件重复执行，也没有将其称为真实 API/Windows 编译测试。

## 真实误报与最小范围

真实 CH03 首次审阅把 `S02.U03` 的合法复合极限证明（带 `g(x)≠b`）引作 `S04.U05` 连续复合证明中的错误。目标 U05 的 epsilon-delta 证明实际正确，保存版本逐字一致，旧流程仍触发了两次不必要补丁。仅检查 issue.unit_id 在实际单元集合里，不能阻止“真实 ID + 别处引文”。

候选只在显式把长引文归给目标、引文在目标不存在、却唯一正向定位到本次实际提供的另一单元时提出归属冲突。匹配只去空白，不抹去否定、关系符号或下标；允许定位长中文原句，不把转述公式当数学等价证明。检测本身不撤销原问题、不修文、不重新分配到来源单元。

这个窄范围可接受：普通缺条件批评没有引文，或短公式、多处重复、转述无法唯一匹配时，不会假称已经证明归属错误。它也不是覆盖所有模型误报的通用系统。

## 已核查的关键边界

1. **合法跨单元依赖批评保留。** 批评如果准确引用源定理并指出目标没有满足分母非零等条件，不触发错误归属删除。如果存在错误归属，但重新核对后目标确实错误使用依赖，`dependency_supported` 可保留原目标 blocking/review；不会因“引文来自别单元”就清空问题。
2. **每个原冲突都要明确裁定。** issue_index/issue_hash 一一覆盖、没有重复或遗漏。空 decisions、unresolved、缺目标反证、错误来源引文等不能变成通过。保留其他原问题，不以空 issues 取代整份审阅。
3. **证据须来自真正提供的正文。** target_spans 必须属于原目标且逐字存在；source_spans 仅限正向匹配来源且逐字存在。支持问题仍限原目标，禁止把来源错误改派到当前修复范围之外。撤销仍依赖普通模型解释这些原文的数学含义；本地 span 核对不能冒充形式证明。
4. **状态先保存，完成裁定不重抽。** 原审阅、输入、冲突、响应及 SHA 留存。已收到有效 unresolved 或不可采纳响应后，同任务 retry 保持阻断；已收到可采纳响应会消费/验证现有文件；发现写入后尚未登记的孤立 response 文件则阻断，不另抽一次。
5. **仅无完成响应的传输失败可继续原核实。** `TRANSPORT_PENDING` 继续相同保存输入的 attribution 请求，不再次普通 reviewer 抽签。此重试允许已有模型路由处理超时/不可用，但不等于允许收到不满意数学裁定后不断抽取。
6. **缓存身份及租约正确。** 单元、先修、计划、模型/检查契约变化会改变身份；新的正式 job 重新审阅，同 job retry 重放。helper、核实 prompt/schema 已纳入 section check contract；helper 独立变更也不能继续使用旧 CHECKED 的依据。状态、证据、pointer 写入经过 `assert_fence`，过期 worker 不得写入。

独审提出的两项问题已在最终候选落实：

- 旧候选在普通审阅覆盖重试之前冻结 payload，第二轮成功时实际模型输入可能多了 `review_validation_feedback`。本版保存 `accepted-review-input.json`、accepted hash，并把真正接受的 payload 用作核实上下文，同时保持初始身份供重放；恢复还校验移除该反馈字段后正文/范围必须一致。新增 scope 重试回归覆盖它。
- 原先代码已有孤立 response 阻断，但缺相应回归。现已补模拟崩溃后孤立文件的测试，断言不新增调用。另补新正式 job 与同 job retry 区分、失效 worker 租约不得写入的测试。

### 最后错误码与预算恢复窄差异

已将此前审过的隔离 helper（SHA `62759e27...`）与最终 helper 逐行比较。差异只包括两处 `REVIEW_EVIDENCE_UNRESOLVED` 改成 `REVIEW_EVIDENCE_BLOCKED`，以及异常证据/状态/事件/pointer 全部保存后，若原错误是 `BUDGET_EXHAUSTED` 则原样重新抛出。数学裁定、定位范围和完成响应禁止重抽的规则未改变。

实际读取 Worker 可见它按错误码中的 `BLOCKED`/`BUDGET` 等关键字分类；前一改动使未解决的归属疑点进入 BLOCKED，而非误记普通 FAILED。内部已完成但未解决裁定的状态仍是 `UNRESOLVED`，再次 retry 仍报 BLOCKED，不重抽模型。Service.retry 明确识别 `BUDGET_EXHAUSTED`，因此保留原码可沿用增额协议。预算耗尽尚无完成模型响应时，保存状态是 `TRANSPORT_PENDING`，增额恢复会继续既有 attribution 输入，不重新请求普通 reviewer。

新增 mock 节点 `test_request_budget_error_preserves_existing_increase_and_retry_protocol` 已纳入最后 74 项，验证原预算错误码、pending 状态、恢复后原问题裁定及普通 reviewer 仅调用一次。该节点不冒充实际 UI 增额全链测试；部署后完整回归仍由 root 执行。最终 helper 语法 AST 重新通过。

## 合并后的验收边界

本独审 API 调用 **0**，生产写入 **0**，新增 Windows 编译 **NOT_RUN**，教师验收 **NOT_RUN**。独审实际执行的是 SHA 核对、AST 解析、旧新 helper 窄差异比较及 JUnit/manifest 解析，74 项为已读取的实施者 mock 回归证据。候选真实 API 定点核实若由 root/实施者另行执行，应使用其独立原始响应和日志，本报告不借此声称已经实测。

合并应按 manifest 锁住文件基础 SHA；完成部署后仍需跑当前版本顶层回归，并确认正式反馈请求进入相同 guard/恢复链。原 CH03 错引样例应撤销错误归属且保留其他问题；合法依赖反例应继续阻断。不能把“mock 能遵守 schema”理解为真实模型一定给出正确裁定。
