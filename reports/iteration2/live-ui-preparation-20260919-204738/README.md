# 真实交付与阻塞 UI 只读脚本准备记录

两份脚本的 AST 解析与 `--help` 均通过。静态扫描未发现 POST/PUT/PATCH/DELETE 或 click/fill/check 等交互调用。浏览器运行、真实 HTTP、模型调用、教师验收均为 **NOT_RUN**；本轮没有启动服务，也未修改产品模块或真实数据库。首次创建报告目录因 Windows 写权限失败，原错误与后续重试方式保留在 [preparation.json](preparation.json)。

只有 root 确认服务已就绪后才执行。完整交付脚本新增可重复的 `--case`，保留原 `--cases`：

```powershell
.\.venv\Scripts\python.exe -B scripts/verify_live_delivery_ui.py --base-url http://127.0.0.1:8766 --case smoke --case CH01 --case CH02
```

只选择当时已经就绪的任务，不能以子集通过代表全部章节完成。实际阻塞任务使用独立脚本：

```powershell
.\.venv\Scripts\python.exe -B scripts/verify_live_blocked_ui.py --base-url http://127.0.0.1:8766 --case CH03
```

阻塞脚本要求真实任务状态为 `BLOCKED`、错误为 `BUDGET_EXHAUSTED`，且无活动 job。检查真实 API 标识、原失败消息、预算与累计计数、显式扩额控件为空和重试门槛；不填写表单、不点击任何工作流按钮。检查点显示 `PARTIAL`、计划关联说明和哈希，所有可用 PDF/TeX/checkpoint 下载须 HTTP 200、响应 PARTIAL 标记、公布 SHA 与字节 SHA 一致。刷新后须恢复同一任务。

两脚本的浏览器拦截器仅允许同源 GET，显式 API 请求也只有 GET。阻塞报告保存全部浏览器/API 请求、console、page errors、截图和下载文件；前后 run、预算与 partial 快照一致性覆盖 count、reviews、审批、失败、job 和产物。

阻塞报告分别记录 `workflow_status=BLOCKED`、`ui_checks=PASS/FAIL`、`full_delivery=NOT_RUN`。界面检查通过不代表整章完成或教师批准；若任务已恢复或状态改变，阻塞身份检查失败，并保留失败/部分证据。输出为新的唯一目录，拒绝覆盖既有记录。

本目录证据为静态准备，没有宣称真实 Edge 检查通过。两脚本 SHA 与实际 `--help` 输出见 [preparation.json](preparation.json)、[交付命令帮助](verify_live_delivery_ui.py.help.txt)、[阻塞命令帮助](verify_live_blocked_ui.py.help.txt)。
