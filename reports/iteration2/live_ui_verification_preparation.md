# 真实产物 UI 验收脚本已准备，尚未执行

脚本：[scripts/verify_live_delivery_ui.py](D:/研究生阶段/数学教学agent/math-teaching-agent/scripts/verify_live_delivery_ui.py)。本记录只证明脚本已编写并通过 AST 静态语法解析；未导入或运行脚本，未启动浏览器，未访问 8765/8766，未调用模型。必须等待实际章节 driver 完成和 root 启动对应服务后再执行。

接口依据为当前 `app.js` 与 FastAPI 路由：`localStorage['math-agent-run']`、`#main [data-testid=run-status]`、`.tag.live`、`a.artifact-link[data-artifact-id]`、`.page-review[data-page-id]` 及 `GET /api/runs/{run_id}` / `GET /api/artifacts/{artifact_id}`。SHA256 来自服务实际数据库公布的产物记录，不以旧 benchmark 报告代替。

待服务已就绪后的命令：

```powershell
.\.venv\Scripts\python.exe scripts/verify_live_delivery_ui.py --base-url http://127.0.0.1:8766 --state reports/iteration2/live-lectures/benchmark_state.json
```

默认检查 `smoke CH01 CH02 CH03`，从 state 读取其实际 run_id，缺失或非 live run 将失败。默认输出为新的 `reports/iteration2/live-ui-<UTC时间戳>-<随机后缀>`；可用 `--output` 指定该目录下尚不存在的目录，拒绝覆盖既有记录。`--cases` 可选明确子集，但子集结果不能冒充全部四项验收。Edge 可由标准安装路径找到，或用 `MATH_AGENT_BROWSER_PATH` 指定实际 `msedge.exe`。

每个任务分别检查：

- 真实 API 标记、服务状态与当前 run_id 一致；刷新后依靠应用自己的存储恢复同一任务。
- 所有非 PNG 产物的下载链接及公布 SHA、全部物理页预览条目、PDF 预览入口；实际加载首末页图像并保存截图。
- 通过 Playwright APIRequestContext 对全部产物执行实际 GET，必须 HTTP 200 且字节 SHA256 与数据库公布值一致。所有 PNG 都检查签名和哈希；保存最新公布的一份 PDF 和源码 ZIP，ZIP 另检查 CRC 和 TeX 成员。
- 前后对比状态、模型请求计数、计划审批、reviews 和产物记录；全部保持一致才通过此项。

脚本不导入应用模块或 User 环境，不启动/停止服务，不点击任何按钮，不提交确认/执行/重试/取消/教师审核。浏览器请求拦截器只允许同源 GET/HEAD/OPTIONS；APIRequestContext 代码仅有显式同源 GET 且不跟随重定向。浏览器子进程不继承 `MATH_AGENT_API_KEY` 或 `OPENAI_API_KEY`。

输出包含总报告与各任务的 partial 结果、HTTP/哈希明细、console/page errors、前后快照、截图和下载文件；失败也保留已完成证据和可用的失败下载体。JSON 标记 `teacher_visual_review=NOT_RUN`，脚本退出码为 0 仅代表全部所选自动检查通过。此处没有逐页教师视觉或数学验收，也没有形式化证明；检查既有真实产物不等于本脚本执行了真实模型 API 测试。
