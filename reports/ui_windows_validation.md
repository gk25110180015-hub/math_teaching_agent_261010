# 本地界面与 Windows 脚本验收

记录日期：2026-09-20（Asia/Shanghai）。本报告仅覆盖 UI 子任务的实际证据，不替代三章真实资料矩阵、真实 API 或教师审阅。

## 实现范围

- `src/math_agent/web/static/index.html`、`style.css`、`app.js`：真实 FastAPI 界面，两工作流输入、MOCK/真实 API 区分、显式输入信任确认、结构化题目和末项自定义、精确单元删除、授权新增、大纲标题编辑、计划差异、确认与执行、重试与取消、后台状态、事件、源内容对照、PDF/ZIP/TeX/报告下载以及逐页人工复核入口。
- 审批和进度取自后端；浏览器只保存最近任务 ID。旧轮询响应不会覆盖用户刚提交的新计划。
- 新增正文支持安全数学 TeX，并明确按输入加入。内容与决策审核和逐页视觉审核分别提交；未通过门禁的产物不能通过按钮强行发布。
- `scripts/*.ps1`：安装、doctor、启动、停止、分层测试及公共函数。使用项目 Python 和项目 uv 缓存，不更改全局 Python、PATH、已保存的 PowerShell 执行策略或防火墙。后台进程以 PID、exe 路径和启动时间验证身份，停止仅针对本项目树，保留数据库和产物。
- `tests/e2e/test_browser_workflows.py`：实际 Edge 浏览器与独立服务/worker；使用 MOCK 供应商和真实 XeLaTeX，保存截图、Playwright trace、控制台记录、日志和任务工作区。

## 本机环境

Setup/doctor 实测：Windows 11 `10.0.26200`，Python `3.12.4`，XeLaTeX `D:\texlive\2024\bin\windows\xelatex.exe`（TeX Live 2024）。启动/停止验收工具环境为 PowerShell `7.6.5`。最终浏览器测试脚本另在 Windows PowerShell `5.1` 进程执行。

浏览器：`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`，实际无头浏览器。产品运行不要求 Node；本机已有 Node 曾用于 JS 语法检查，但不属于启动或构建依赖。

## 已执行的验证

| 项目 | 实际结果 | 证据 |
|---|---|---|
| 六个 PowerShell 文件语法解析 | PASS | 本机 PowerShell AST parser，零语法错误 |
| JS 语法 / E2E Python 语法 | PASS | `node --check .../app.js`、`python -m py_compile .../test_browser_workflows.py` |
| Setup-Windows | PASS（修复后） | `windows_setup_smoke_retest.log`；43 包按锁检查，随后 doctor 成功 |
| Run→新建任务→Stop→Run→恢复同一任务→Stop | PASS | `windows_script_smoke.json`、`windows_script_smoke.log` |
| 中文、空格、括号工作区 | PASS | 上述脚本使用 `workspace/Windows 集成(恢复)` |
| 最后 4 个强化浏览器用例 | PASS | `test-runs/20260920-003846-307-browser.{log,json,xml}`；41.42 秒 |
| FDU 模板适配摘要 | PASS（界面与产物断言） | 计划与刷新后的确认记录中可见；实际导出使用 FDU；`e2e/20260920-003847/test_beamer_exact_deletion_and_addition.png` |
| 真实 API 未配置提示 | PASS（仅显示验证） | 下拉及说明显示未配置或未启用；`e2e/20260920-003847/live-unconfigured.png`；切回 MOCK 后才提交任务 |
| 真实 API | NOT_RUN | 测试进程显式关闭真实调用、清空 API key 环境值 |
| 教师数学/视觉审核 | NOT_RUN | 测试从未点击人工审核通过；成功任务停在 `AWAITING_USER_REVIEW` |
| 三章真实参考矩阵 | 不由本报告认定 | 本报告的课件/讲义 fixture 均为合成输入 |

最终脚本命令：

```powershell
# 在 math-teaching-agent 项目根目录执行。
.\scripts\Setup-Windows.ps1
.\scripts\Run-Local.ps1 -Port 18765
.\scripts\Stop-Local.ps1

# 仅新建进程使用 RemoteSigned；没有修改全局或用户持久策略。
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
  -NoProfile -ExecutionPolicy RemoteSigned `
  -File .\scripts\Test-Windows.ps1 -Suite browser
```

启动/恢复实测额外设置了进程环境 `MATH_AGENT_WORKSPACE` 为独立中文测试工作区，并使用 `Invoke-RestMethod` 保存、重启后读取同一 MOCK 任务。任务 ID 和路径在 `windows_script_smoke.json`。验证结束已停止测试服务。

## 最终 E2E 断言

1. 讲义：所有题目末项为自定义，默认未代选；提交选择、编辑标题、确认、执行、刷新后保持原审批，最终到达待人工复核；真实 PDF、完整 ZIP 和所有物理页 PNG 均可读取。
2. Beamer：从中文文件名上传，显示两模板选项；最后一轮本机实际选择 FDU，核对页眉/完整三态目录适配摘要明确可见且刷新保留；精确删除例 3 及关联题解、加入指定章节的新增正文；确认执行后真实产物存在；独立读取 ZIP 内实际 TeX 核对 FDU、授权新增存在且例 3 已删除，忠实度报告为 PASS。
3. 自定义：实际选择并填写文本，解析效果进入计划，刷新后仍存在。
4. 编译失败：实际编译报告为 FAIL 且包含 `UNDEFINED_CONTROL_SEQUENCE`；错误状态、日志和产物保留；点击重试后没有返回确认页。

最终证据目录：`reports/e2e/20260920-003847/`。构建与数据库保留于 `workspace/t/3f550a70/`，该次服务使用临时端口 `54116`，测试后已停止；本轮未启动最终 `8765` 常驻服务。最后一轮结果为 **4 passed, 100 deselected, 2 warnings，41.42 秒**；四份浏览器控制台错误记录均为空。两条成功路径的模型来源均为 MOCK，真实编译与页面渲染不等于真实模型教学能力或教师验收通过。

此前 `reports/e2e/20260920-001243/` 的强化通过记录（43.94 秒，默认 Beamer）保留用于历史比较。本次复测在 PDF 检查与交叉引用实现完成、相关后端回归稳定后执行，没有放宽业务断言。启动 README 与脚本参数、手动双终端入口、环境变量继承及 UI 主文件输入已核对一致。

## 已保留的失败及纠正

- 最初受限 shell 无权写日志/工作区；相关命令未完成，不计通过。经工具授权后在同一项目执行验证，没有使用管理员安装或改变系统设置。
- 默认 Windows PowerShell 5.1 策略阻止加载脚本；该次业务测试为 NOT_RUN。后续只为新建测试进程指定 RemoteSigned。
- Setup 初测遇到 uv 默认缓存与临时目录跨盘的 `os error 17`；失败输出在 `windows_setup_smoke.log`。修为明确复用项目 `.uv-cache` 后通过。
- 初次浏览器测试使用的字符串求值等待被严格 CSP 拒绝；改为 locator 断言，未放宽 CSP。
- 早期 `20260920-000051` 和 `20260920-000437` 报告中的 4 PASS 只检查了 UI 操作与失败恢复。后续审查发现真实构建因 Windows 长路径失败，故这些结果**不能作为业务完成或编译成功证据**。原始日志、trace、截图和工作区未删除。
- 强化断言后又暴露了默认 Beamer `solution` 重复定义。后端缩短临时/构建路径，渲染器修正环境冲突后，最终强化用例通过。完整证据修正说明在 `e2e/ACCEPTANCE_NOTES.md`。
- 最终 pytest 的 2 条警告为已锁依赖的 deprecation warnings，不是数学/排版审核结论。
- 最后受控复测的初次尝试遇到并行开发中的 `math_agent.crossrefs` 暂未落盘，pytest 收集失败，四项浏览器业务未运行；记录在 `test-runs/20260920-003620-699-browser.log`。等待模块及其回归完成后再运行最终全部四项；未删除或忽略该新测试。

未执行、缺少条件或需要教师判断的项目继续保持 NOT_RUN / NEEDS_REVIEW；本报告不声明 M5 全部完成。
