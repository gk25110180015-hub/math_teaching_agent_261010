# 全量回归中一次数值核算 UNKNOWN 的调查

先前 [599 通过、1 失败的完整快照](local-final-20260920-112433.md)中，`test_actual_ch02_evidence_remains_numeric_and_review_required_but_not_repair_target` 期待 `numeric_spotcheck_passed`，实际收到 `not_checked`。当时断言没有输出完整证据，无法从旧日志确定子进程返回、解析或数学计算中的具体原因。该节点耗时 0.80649 秒，因此不能把它描述为已证实的 8 秒子进程超时。

**根因尚未定位，没有声称修复。** 所有 UNKNOWN 继续作为该测试的失败；产品算法、核算超时及断言预期均保持原样。

## 已执行的离线调查

- 同一原始 fixture 连续运行 `check_math` 10 次，另直接运行数学子进程 3 次：均返回正常数值抽查结果，3 个子进程返回码均为 0，无 stderr。[完整结果](numeric-diagnostic-20260920-113009-490177.json)
- 按原顺序运行临近的 `test_model_routing.py`、`test_multimodel_configuration.py`、`test_multimodel_workflow.py`，再运行异常数学节点；3 个独立进程各 55 项通过。目标节点执行前均只剩 MainThread，cwd/python/stdio 正常，两家密钥为空、live=false；未观察到这些前序用例的环境或线程污染。这只能说明该范围内未复现，不能证明全局不存在污染。[三轮摘要](numeric-order-20260920-113312-336169/summary.json)
- 初次只给失败断言附加完整 result。随后为下一次全量增加目标单测试内的透明子进程诊断：仍调用真实 Popen、真实 communicate、原 8 秒时限，并返回原 stdout/stderr；记录输入、返回码、stdout/stderr 与 `check_math` 完整结果到测试临时目录的 `math_child_diagnostic.json`。monkeypatch 仅在该测试生命周期生效。诊断版本单项通过：[日志](numeric-child-diagnostic-test.log)、[JUnit](numeric-child-diagnostic-test.xml)。

以上均未调用远程模型，也未改变旧讲义、预算或原始资料。计数与全量和其它定向回归重叠，不能相加当成独立样本。

## 最终全量复测

[完整快照 local-final-20260920-113521](local-final-20260920-113521.md)实际为 **600 passed、0 failed/error/skipped、1 real_api deselected、2 warnings**；pytest 212.51 秒，120 个源码/测试/配置/模板/锁文件前后 SHA 一致。20 个 Windows 标记节点 call 与 JUnit 均通过，包含预期失败/取消/安全限制探针，不能称为 20 份 PDF 编译成功。浏览器、真实 API 及人工视觉未计入该套。

原异常数学节点本次返回码 0、stderr 空、`numeric_spotcheck_passed`，原 8 秒核算超时未变。整体数学状态依然为 `NEEDS_REVIEW`，数值单点抽查并未升格为证明。完整输入与子进程结果保留在 `workspace/t/mmfb575198d/test_actual_ch02_evidence_rema0/math_child_diagnostic.json`。

本次通过未解释先前 UNKNOWN 的原因，因此旧失败仍保留为原因未知的观察，没有声称产品逻辑已修复。[全量结束后的 53 份原始资料 SHA 复核](originals-recheck-20260920-113945-235484.json)全部一致。
