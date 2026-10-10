# Benchmark 重检版本选择候选

**未部署生产源码。** 合并入口为 [manifest](待合并/benchmark-recheck-manifest.json)，仅替换 `src/math_agent/benchmark.py`，候选 [benchmark-recheck-current.py](待合并/benchmark-recheck-current.py)，窄差异 [patch](待合并/benchmark-recheck-current.patch)。部署前应核对 manifest 的 baseline SHA；当前原文件 `710e7950b72e6f7259f706f04b716faaf33ca88f81b10601c3a1dbb711f2b54b`，候选 `d0cd29836457a8fec93cfb5489e52825566c7416b277403511c4428bd0c7c434`。

旧分析器在正式 recheck 将旧产物标记 superseded 后仍将其质量/PDF 信息当作当前结果；还丢失其他 revision 的历史、未核查 step 计划身份和 SHA。已用实际 Service.recheck + 隔离 SQLite 复现，并保留红测证据。

候选行为：

- artifacts 查询保留任务所有 revision、status、created_at、rowid 与文件 SHA 核查；当前摘要仅采用当前已批准 revision、非 superseded、同名中按 `created_at DESC,rowid DESC` 最新的一份。最新文件 hash 失败时不回退到旧 PASS。`selected_for_current` 与 `artifact_selection.current_artifact_ids` 可明确区分当前和历史。
- steps 同样按时间/rowid 明确倒序；按 `plan.sections` 顺序选择每节最新版并生成统计。验证当前 plan 内容 hash、审批 hash/revision/input_hash；复用 Pipeline 的现有身份、source、schema、SHA 和 legacy 前缀验证方法。其他计划身份跳过；最新合格行损坏则保留 BLOCKED 证据，不回退更旧正文。
- 为复用纯校验方法创建未初始化的 Pipeline 对象，仅设置只读校验需要的属性；不调用 Pipeline.__init__、不创建 provider、不开启预算、不生成 prefix proof、不写数据库或事件。legacy 仅在已可验证时读取。
- 输出 `checkpoint_selection` 的历史、选中行和错误。此分析不会重跑任何数学/模型/编译检查，也不把“可验证的历史批准正文”升级为“刚刚完成本轮重检”。`freshness` 字段明确这个边界。

新增 [test_benchmark_recheck_versions.py](../../tests/test_benchmark_recheck_versions.py) 有 8 个参数化节点：真实重检后的旧产物失效；新旧 revision 的选择与历史保留；同时间 rowid/错计划/批准顺序；源文件损坏；checkpoint SHA 损坏；legacy 无初始化/数据库副作用；审批失效；坏的新产物不回退到旧文件。

|实际执行|结果|证据|
|---|---|---|
|旧生产实现跑新增回归|8 FAIL（红测）|[日志](benchmark-versions-red-20260921-000045.log)、[JUnit](benchmark-versions-red-20260921-000045.xml)|
|隔离候选 + 全部既有 benchmark 专项|26 PASS，1.62 秒|[日志](benchmark-versions-candidate-20260921-000101.log)、[JUnit](benchmark-versions-candidate-20260921-000101.xml)|

以上都是离线/mock 测试，使用实际 SQLite 和 Service 状态迁移，PDF/检查报告内容为明确的合成 fixture。真实 API **NOT_RUN**、真实 Windows 编译 **NOT_RUN**、PDF 视觉及教师验收 **NOT_RUN**。测试运行脚本清空所有模型配置/密钥、禁外网 socket、使用新独立临时目录；日志与产物未删除。
