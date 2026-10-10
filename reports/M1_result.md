# M1：持久化 mock 闭环

已实现 `domain.py / store.py / migrations/001_initial.sql / service.py / worker.py / web/`：计划版本/哈希、真实选择、自定义候选效果、大纲编辑、审批、幂等排队、独立 worker、租约/心跳/fencing、取消、事件、产物按 ID 访问与页面恢复。

先写失败测试后实现。初次基础 Python 收集测试因缺 pydantic-settings 未运行；项目隔离环境安装后 `M1_core_first.log` 为 20 passed。mock 讲义完整流程真实 XeLaTeX 编译并全页渲染：`M1_mock_lecture_first.log` 为 1 passed。

最终强化浏览器证据见 `ui_windows_validation.md`：讲义和 Beamer 均达到 AWAITING_USER_REVIEW，实际下载并检查 PDF/ZIP/全部 PNG；重复执行、版本修改、删除与新增、刷新和错误重试均有自动化回归。原始过宽 E2E 只验证操作状态、曾误把路径异常纳入流程通过，已在 `e2e/ACCEPTANCE_NOTES.md` 纠正并保留原证据。

关键回归：用户精确删除例题及关联解答合法；确认后执行/失败重试不回确认；旧计划/旧 worker 提交被拒绝；取消后不提交晚到结果。所有模拟供应商和模拟复核动作都属于测试，不算真实 API 或教师验收。

恢复：保留数据库和 workspace，重新启动 server/worker；失败任务点击重试。输入或内容计划变化需要新版本/新任务，不能沿用旧批准。
