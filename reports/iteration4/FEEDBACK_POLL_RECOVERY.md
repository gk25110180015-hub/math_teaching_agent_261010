# 回执显示与事件日志刷新解耦

V4 第一次完整 Edge 验收为 **13 PASS / 1 FAIL**，不是全部通过。证据位于 `final-deployed-e2e/20260922-043328-aa8704/`，原始 JUnit、服务器日志、trace、截图和十个隔离数据库均保留；源码和测试 SHA 未变，人审记录为零。

失败 trace 显示定时器已经收到包含新回执的成功 GET；随后事件日志 GET 一直未完成，界面因此未应用已收到的任务状态。此次没有后续旧 GET 覆盖新回执，也不能归因为 busy/hidden。事件请求原始停滞的底层原因尚未确定。旧版 `refreshRun` 要等待事件请求后才更新 `state.run` 和 DOM，使两个独立结果耦合。

候选仅将已通过任务 ID/epoch 校验的 run 状态及 fingerprint/DOM 更新移到 events 请求之前；events 仍在返回后复核任务 ID/epoch 再追加日志。未修改模型、超时、工作进程、请求预算或 Python 生产源码。

新增的确定性场景持续返回同一新回执，并暂扣随后事件请求。它不手动触发刷新：必须由实际定时器获取新回执，在 events 尚未放行时于原 10 秒内显示新文本并保留草稿，然后释放事件请求、移除路由、刷新页面，继续原空反馈撤回及审批/预算/历史保持检查。

| 验证 | 结果 | 证据 |
|---|---|---|
| 原部署 UI + 暂扣 events | 1 FAIL，预期 RED；39.01 秒 | `feedback-poll-validation/red-20260922-093722-6c6c22/` |
| 浏览器仅替换候选 JS + 相同暂扣 events | 1 PASS；32.49 秒 | `feedback-poll-validation/green-20260922-093829-0849b9/` |

两次观察都记录实际 run GET 命中 1 次、暂扣 events 1 次且尚未释放，busy/editing/hidden 均为 false。旧版仍持有旧回执，候选已显示新回执并保留草稿。GREEN 继续完成原场景，实际 Windows 编译通过，未提交人审。两次生产源码与测试全部 SHA 不变。模型均 mock，真实 API 和教师验收 NOT_RUN。

`feedback-poll-candidate/manifest.json` 提供原版及候选精确 SHA。部署用测试去除了 reports 专用的 JS 注入及路径设置，保留同一暂扣事件场景和全部原断言。候选通过不能替代部署后的完整 14 Edge 验收；部署及新全套结果另记。
