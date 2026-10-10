# 不安排练习与计划必需类型冲突修复

实际问题：planner 可在各节 `required_kinds` 中列出 exercise；用户随后选择 NONE 时旧 Service 只把 `lecture.exercises` 设为 none，导致 writer 被要求同时“不能生成练习”和“必须生成 exercise”，本地内容门禁也会互相冲突。

修复只改 `service.py` 的计划决策事务。在该事务内按明确枚举选择同步各节必需类型：NONE 移除 exercise；若该节没有例题，移除与 exercise 一同要求的 solution；例题仍保留 solution。WITH 确保 exercise 和 solution 各出现一次。自定义语义不做猜测。数学目标、定理／定义／证明、先修顺序和原始资料不改动。

实际衍生变化写入同一 decision 的 `derived_section_requirements`，并在计划 diff 中展示 sections。Store 按原机制生成新 revision/hash；旧计划与旧审批历史保留，但新 revision 必须重新确认，旧 hash 不可执行。

先红 fixture：`exercise_policy_red.log`，1 failed / 3 passed，复现 NONE 后 exercise 仍必需。修复后针对新策略与原 state／benchmark actor 回归：**14 passed in 1.61s**，日志 `exercise_policy_validation.log`。另运行原规划选择持久化与 Beamer 授权删除两项定向工作流：**2 passed, 1 deselected in 0.46s**，日志 `exercise_policy_workflows.log`。

这些都是离线逻辑／mock 工作流测试；本子任务 **未运行真实 API、Windows 编译或全套测试**，不代表教师验收。原自然语言 objectives 完整保留；若其文字仍描述被取消的练习，当前明确选择及衍生 required_kinds 应作为实际约束，由 writer 根据锁定选择落实，不按关键词自动删除数学目标。
