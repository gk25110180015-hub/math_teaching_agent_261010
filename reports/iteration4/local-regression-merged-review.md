# 已合并实现的完整本地回归

最终轮 **728 PASS / 0 FAIL / 0 ERROR / 0 SKIP**，动态收集 59 个顶层 `tests/test_*.py`；排除 1 个真实 API 测试，嵌套浏览器 E2E 由独立任务测试，不计入这里。运行时间 2026-09-20 23:32:48—23:36:09（+08:00），201.313 秒。两轮及专项之间不累加为独立测试总数。

|执行|结果|证据|
|---|---|---|
|生产排版恢复专项|20 PASS；其中 1 个实际 Windows XeLaTeX 失败→局部修复→重编译测试，模型均 mock|[日志](compile-recovery-deployed-20260920-232631.log)、[JUnit](compile-recovery-deployed-20260920-232631.xml)|
|完整首轮|726 PASS / 2 FAIL；这一轮不是通过|[完整记录](local-full-20260920-232705-e4d52e9e.md)、[日志](local-full-20260920-232705-e4d52e9e.log)|
|两处 fixture 适配专项|12 PASS；含实际 Windows 答案编译|[日志](fixture-contract-targeted-20260920-233212.log)、[JUnit](fixture-contract-targeted-20260920-233212.xml)|
|完整最终轮|728 PASS；21 个 Windows compile 标记节点全部断言通过|[逐节点记录](local-full-20260920-233248-60b03228.md)、[JSON/SHA](local-full-20260920-233248-60b03228.json)、[日志](local-full-20260920-233248-60b03228.log)、[JUnit](local-full-20260920-233248-60b03228.xml)|

## 两处失败的原因及改动

1. `test_completion_pipeline_compiles_answers_at_end_with_numbered_link` 已确认数学和编译 PASS，随后旧 `sS01*/source/lecture.tex` glob 找不到实际位于 `compile-attempt-1/source` 的文件。现在按照最终 `compile_attempts` 的 `source_key` 读取，并额外验证源码字节 SHA 与证据一致；末尾答案、题号回链、原正文和审批保留断言未删除。
2. `NumericProvider` 的 mock reviewer 只支持局部审核，遇到新增 `chapter_coverage` 时误取局部专属 `tool_checks`。现在分别记录 `section_local → chapter_coverage`；局部仍确认真实符号工具返回 `numeric_spotcheck_passed`，整章 mock 明确为中性审核；仍断言局部审核 1 次、修复 0 次、配额不消耗。真实数学错误及 mock 审核不因此被放宽。

首轮失败日志、JUnit 和隔离临时目录均保留。两轮源码快照比较仅上述 **2 个测试文件**发生变化，生产 src、提示词、配置均未改变；每轮内部 SHA 全程稳定。

## 证据边界

- 模型：密钥清空、live=false、streaming=false、provider=mock；本 Python 进程阻断非 loopback socket.connect，阻断尝试 0。真实模型 API **NOT_RUN**。该审计钩子不继承到子进程；数学/TeX 子进程使用现有隔离环境，不将此写成系统级网络防火墙保证。
- 本地：最终轮包括 `test_series_domain_worker.py` 两项实际独立 SymPy 子进程域检查，以及新增 global contract 和编译局部恢复回归。
- Windows：21 个带 `windows_compile` 标记的节点实际执行、无跳过；其中包括故意破坏编译、取消、溢出和外部写入限制探针，断言通过不能解释成 21 个正常 PDF 均成功生成。逐节点用途与结果见最终 JSON/Markdown。
- 教师数学审核、人工视觉验收 **NOT_RUN**。这些软件回归不等于最终 CH02/CH03 教学语义覆盖通过。
- 两条 warning 为 Starlette/httpx 和 anyio 的弃用提示，保留在日志中；未在本轮扩改依赖。

最终隔离产物目录：`workspace/t/i460b03228`；首轮失败产物：`workspace/t/i4e4d52e9e`。SHA 快照覆盖 164 个源文件、提示词、配置、模板、测试、脚本和锁文件。

|关键文件|最终 SHA-256|
|---|---|
|pipeline.py|`504e66ea5d2abaec818deafa3420ec70db82fbdee59638fed1c64e8383250fa8`|
|compile_recovery.py|`aad2764ca6751343fb79b4e29ced6822a245584b1782185d928f727b8e3c63ab`|
|mathcheck.py|`85967c8d3dbfb8e0442e1863e4f21654e46206ee130b4b51df69ef5f7964a588`|
|reviewer_math.md|`cd75bbcf1516a0fa5ecaa882e753956e82d65da7e0640442db98717a1cf6f92d`|
|repair_local_patch.md|`362fb34b2529572af9620c5433dbb223290c519889e89192c1d52c5d65e60943`|
|run_iteration4_regression.py|`c4a7c4ed2c225c01af65a1a9b6d3c6473707186f7ab1ac2e426102782cc7fa6a`|
