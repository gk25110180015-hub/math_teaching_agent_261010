# 独立工作区脚本检查

2026-09-20。`Run-Local.ps1` 与 `Stop-Local.ps1` 新增可选 `-Workspace`。省略时仍为工程 `workspace`，显式路径须在该目录内；相对路径基于工程根目录解析。拒绝越界、相似前缀和重解析点。所选目录内使用独立的 `agent.db`、`runtime/local-processes.json` 与 `logs`。

进程记录新增 `workspace_root`。启动检查旧记录所属项目/工作区；停止继续核对项目、工作区及 PID/可执行文件/启动时间。旧版本缺少 `workspace_root` 的记录仅允许在默认工作区使用，便于停止此前已启动的默认实例。`MATH_AGENT_WORKSPACE` 仅在启动子进程期间覆盖当前进程值，finally 恢复原值。未改变 Windows User 环境。

实际命令：

```powershell
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
  -NoProfile -ExecutionPolicy RemoteSigned `
  -File reports\iteration2\ui_workspace_script_checks.ps1
```

第二次执行 **25 条断言 PASS**。这是实际 PS5.1 中的**模拟进程测试**：Start-Process、Get-Process 和健康响应使用测试替身；没有启动 server/worker/browser，没有 API 请求，没有执行 taskkill，也没有修改默认 8765 实例。Stop 用不存在的 PID 验证跳过与归档。不能把它写成新参数的真实服务启动验收；最终实际 8766 启动由主任务另行验证。

覆盖默认/相对/绝对工作区，越界拒绝，旧默认记录兼容与非默认拒绝，子进程环境/调用环境恢复，独立日志与进程记录，项目/工作区错配拒绝且保留记录，已退出进程跳过及同工作区归档。重解析点拒绝逻辑已实现和语法检查，本测试没有创建实际 junction/symlink；不称作真实重解析点攻击测试。

首轮在 PS5.1 读取 UTF-8 无 BOM JSON 时失败，中文路径被默认 ANSI 解码。实际 Run/Stop 及测试改为 `Get-Content -Encoding UTF8` 后通过；未放宽路径或进程校验。首轮失败保留于 [ui_workspace_script_checks.log](ui_workspace_script_checks.log)，原模拟目录 `workspace/t/ws-ded50f23` 未删除。最终结果见 [复测日志](ui_workspace_script_checks_retest.log) 与 [JSON](ui_workspace_script_checks.json)，工作区 `workspace/t/ws-a5493838`。

用法已加入 [README](../../README.md)：

```powershell
.\scripts\Run-Local.ps1 -Workspace 'workspace\iteration2-live' -Port 8766 -OpenBrowser
.\scripts\Stop-Local.ps1 -Workspace 'workspace\iteration2-live'
```

真实 API：NOT_RUN。真实应用启动：NOT_RUN。教师视觉：NOT_RUN。
