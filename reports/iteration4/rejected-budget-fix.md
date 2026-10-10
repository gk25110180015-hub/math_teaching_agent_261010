# 拒稿预算恢复回归修复提案

状态：**PROPOSED_NOT_APPLIED**。正在运行的生产源码、数据库及真实任务未修改；没有远程 API 调用。

问题：`LocalRecovery.begin_proposal()` 在同一修复 key 累计两次拒稿后，无论用户把 `local_repairs_per_unit` 提高到多少都会继续 `BUDGET_EXHAUSTED`。错误信息却声称增额后可以继续。

拟议修复位于 [rejected-budget-fix.patch](rejected-budget-fix.patch)，仅调整 `src/math_agent/local_recovery.py`：每个修复 key 的拒稿上限变为 `max(2, local_repairs_per_unit)`。默认预算 2 和旧 0/1 配置的行为保持不变；预算提高到 6 时，已有两次拒稿可以继续尝试，但第六次拒稿之后仍停止。已接受单元修改上限、每 key 提案上限 `预算+1`、总请求限制及严格补丁校验均保留。

原计数、合法候选、未决疑点、审批和拒稿证据不清零；恢复后的状态记录新的预算规则，旧状态由既有 history 归档保留。错误信息分别给出提案和拒稿上限，明确需要提高局部预算；仅提高请求额度不再被误解为解除该局部限制。

验证：

| 检查 | 结果 | 范围 |
|---|---|---|
| 生产原源码红测 | 2 PASS / 3 FAIL | 5 个新增回归；三个失败均复现增额 6 后仍被拒稿 2 次硬阻塞 |
| 提案隔离回归 | 75 PASS，2 个依赖弃用警告 | 新增 5 项、旧局部恢复和预算 API 回归；仅 pytest 进程加载提案模块 |
| 真实 API | NOT_RUN | 合成提案，没有 HTTP 模型请求 |
| Windows 编译 | NOT_RUN | 本次只验证预算、SQLite 和状态恢复 |
| 教师数学/视觉验收 | NOT_RUN | 不属于该软件回归 |

新增测试 [test_rejected_budget_recovery.py](../../tests/test_rejected_budget_recovery.py) 使用真实 Service、Store 和 LocalRecovery，拒稿经过真实严格补丁校验；模拟请求通过生产预发送账本记账。测试验证增额不自动执行、不清审批与计数、拒稿不能成为合法候选、6 次拒稿仍停止、仅提高请求预算无效、局部增额不能绕过原请求上限。

日志：[生产红测](rejected-budget-red.log)、[红测 JUnit](rejected-budget-red.xml)、[提案隔离测试](rejected-budget-proposed.log)、[提案 JUnit](rejected-budget-proposed.xml)。哈希见 [manifest](rejected-budget-fix-manifest.json)。提案完整文本另存 [proposed.py](rejected-budget-local_recovery.proposed.py)，方便在生产任务停止后核对合入。

生产 `local_recovery.py` 在隔离测试前后的 SHA-256 相同：`0a6f2ce936d285102271d293fa12578e203830e31df53dd95bf4a61e893025a1`。合入后仍需直接运行新增及相关回归，不能把本次隔离测试当作生产已部署证明。
