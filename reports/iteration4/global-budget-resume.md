# 全局修复预算增额恢复提案

状态：**PROPOSED_NOT_APPLIED**，未修改生产 Pipeline。补丁 [global-budget-resume.patch](global-budget-resume.patch) 只涉及全局失败导入及 `lecture()` 起始恢复逻辑，可与章节 checkpoint/编译修复补丁按方法区域合并。

原问题：全局状态一旦记录为 `budget_exhausted`，`lecture()` 就无条件返回 `GLOBAL_MATH_BLOCKED`，即使用户已经把持久化全局修复预算从 2 提高到 6。普通重试既不能恢复，也无法正确说明仍需哪个额度。

修改后先比较实际持久化 `global_repair_rounds` 与 `rounds_used`；未提高对应额度仍返回 `BUDGET_EXHAUSTED`，不更改状态或调用模型。额度足够时，将保留的最后失败轮次、全部单元哈希、章节 checkpoint/源码哈希逐一核实，然后直接进入下一修复轮；不会先重新抽取模型审阅来清除旧疑点。

原轮次继续累计，例如 2→3；原 HTTP 请求数、审批、合法稿和未决问题均保留。新候选必须重新做受影响章节及下游章节的检查和编译。恢复验证记录使用独立文件名，`global.budget_resumed` 事件记录原/新轮次、预算版本、有效上限、未清零请求数与原失败证据哈希；自动流程不提交人工审核。

新增 [test_global_budget_resume.py](../../tests/test_global_budget_resume.py) 六项离线回归。原源码 **6 FAIL**，精确复现不可恢复行为；隔离候选加旧全局修复/预算 API 回归 **70 PASS，16.22 秒**。测试使用真实 SQLite/Service/请求账本及 mock 模型、mock 编译器；真实 API、Windows 编译、教师数学/视觉验收均 **NOT_RUN**。

证据：[红测](global-budget-resume-red.log)、[候选隔离回归](global-budget-resume-proposed.log)、[manifest](global-budget-resume-manifest.json)。生产 Pipeline 前后 SHA-256 为 `350f9eff0d4a8f24937e4c0dfc605f7f2bb928fc603b313d99219553ea628a1c`。

审查另发现一个既有且未纳入本窄补丁的边界：`_load_global_repair_state` 在全局 repair prompt、WrittenSection schema 或 normalizer 哈希变化时会重新初始化轮次为 0。本提案保持原身份策略；如本轮另改这些项目，需要单独迁移同审批下的历史轮次，而不能把新的校验契约视为新的预算。
