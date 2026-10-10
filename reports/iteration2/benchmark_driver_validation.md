# 真实 API 讲义基准驱动与离线验证

实现：`scripts/benchmark_live_lectures.py`、`src/math_agent/benchmark.py`；测试：`tests/test_benchmark_metrics.py`。密钥没有写入脚本，使用应用的 `Settings` 环境读取。驱动不直接拼接 API 请求，统一调用 `Service` 与 `Worker`。

## 测试范围和顺序

先执行严格两节的数列极限 smoke；只有该任务达到 `AWAITING_USER_REVIEW`，才允许依次执行三个正式基准专题：CH01 第一章数列与数列极限、CH02 第二章无穷级数、CH03 第三章函数极限与连续。第四章导数不属于本轮必跑矩阵。

真实方案选择固定且显式记录为：关键定理完整证明、概念与计算均衡、安排练习附答案、答案集中于末尾。通过 `Service(actor='benchmark_driver')` 保存选择和方案确认，不伪装为教师。遇到新问题或计划节数超出本次范围，驱动停止并保留计划，不自动丢弃或截断内容。驱动不调用页面 review 或 publish。

## 实际离线验证

```powershell
.venv\Scripts\python.exe -m pytest tests/test_benchmark_metrics.py --basetemp workspace\benchmark_metrics_03 -q
```

**11 passed in 0.55s**，日志 `benchmark_offline_tests.log`。覆盖条件词与类型计数、所有物理页密度、供应商缺失 usage 不记零、schema 失败与网络超时分开、统计不升级教师 PASS、缺配置不请求且无 mock fallback、真实本地 Service/SQLite 的 benchmark actor／选择／审批／恢复、发送前请求预算、失败报告不可覆盖归档。

随后针对真实首节暴露的统计缺口增加两项教学诊断测试，当前完整结果为 **13 passed in 0.56s**，同日志已更新；新增重复外壳候选、题解关联和空核算请求的显式指标，详见 `live_content_diagnosis.md`。初始失败 fixture 保留于 `benchmark_pedagogy_red.log`。

其中工作流测试使用**假 Worker**，只验证本地编排与持久状态；不是实际 API、实际数学审查或 Windows 编译测试。

另已实际执行独立只读预检：

```powershell
.venv\Scripts\python.exe scripts\benchmark_live_lectures.py --phase all --analyze-only --run-dir reports\iteration2\benchmark-preflight --workspace workspace\iteration2-preflight
```

结果 `LIVE_NOT_RUN`、实际请求 **0**。原始 TeX 仅在本地解析；原始 PDF 全页渲染并保存几何、PNG 及 SHA-256，未修改原件。

| 原始专题 | 可解析有效单元 | 物理页 | 平均可抽取字符／页 | 自动 PDF 几何 |
|---|---:|---:|---:|---|
| CH01 数列与数列极限 | 73 | 9 | 756.222 | PASS |
| CH02 无穷级数 | 64 | 10 | 761.400 | PASS |
| CH03 函数极限与连续 | 97 | 16 | 689.688 | PASS |

原件存在 opaque_tex 单元，计数受解析粒度限制。零个独立 exercise 类型不能据此断言原讲义没有练习。先修字段、源交叉引用、条件词和题解显式关联均分别报告，不把它们当作数学前提完整性的证明。字符密度包含页码／标题，不能替代教师版式判断。

## 真实运行与恢复命令

由主任务在环境准备后执行；此验证记录不把上述离线测试当作真实 API 通过。

```powershell
. scripts/Common-Windows.ps1
Import-AgentUserEnvironment
.venv\Scripts\python.exe scripts\benchmark_live_lectures.py --phase smoke --execute-live --run-dir reports\iteration2\live-lectures --workspace workspace\iteration2-live --per-run-budget 60 --total-budget 240
```

修复条件后同一命令加 `--retry-failed`，复用原 run、审批和检查点，不静默新建任务。需要等待之前 worker 租约到期时会明确停止，不强占仍有效的租约。smoke 自动门禁完成后，把 phase 改为 `chapters`；只分析已有结果时使用 `--analyze-only`，禁止与 `--execute-live` 混用。

每 2 秒保存 `benchmark_state.json`、任务快照及逐请求记录；发送前持久计数。请求预算同时受单 run 与本轮总余额约束。输出记录供应商实际 token、请求耗时、HTTP／schema／业务失败；未报告费用不推算。墙钟耗时包含恢复前停顿，与逐请求耗时分开。

每次重试前及终态分析完成后，将当前比较、快照、请求记录和 driver 状态复制到 `CASE/attempts/attempt-N-原因-唯一时间戳/`；`attempt_manifest.json` 保存错误、job attempt、请求数及文件哈希。新尝试只更新 latest 报告，历史档案不覆盖。数据库 lease 和 checkpoint 仍由原应用管理，崩溃边界请求可能已计费。

## 当前真实证据的边界

主任务的首轮 smoke 已实际获得一次 HTTP 200 与 schema-valid planner 响应，随后业务门禁因 `PLAN_DEPENDENCY` 失败。它不等于端到端通过；原 run `426866cf71d2437bb17b54ac801a8c18` 的错误、一次请求与供应商 usage 留在 `live-lectures/smoke/` 和应用数据库。后续修复、重试与结果以该目录的 latest 比较及不可覆盖 attempt 档案为准。

所有比较总状态保留 **NEEDS_REVIEW**。模型生成文本与原文不同不自动判数学错误；同样，单元数量、页数、密度或自动 math／compile／layout 全 PASS 都不能升级为教师 PASS。正式教师视觉与教学验收仍是 **NOT_RUN**。
