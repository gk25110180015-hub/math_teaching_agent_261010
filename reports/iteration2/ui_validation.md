# 第二轮界面回归：完整原稿书目补齐

日期：2026-09-20，Asia/Shanghai。范围为实际 Edge 浏览器、独立 FastAPI/worker、MOCK 模型、本机 XeLaTeX。没有调用真实 API，也没有替教师提交内容或逐页审核。没有改动产品 UI、后端或原始资料，没有启动或重启最终 8765 服务。

**后续最终全五例已一次通过：5 passed in 55.40s。** 详见 [final_ui_validation.md](final_ui_validation.md) 和其独立日志/JUnit。以下保留第一次书目新增回归的历史结果，不把旧失败改写成通过。

## 实际结果与证据

| 验证 | 结果 | 证据 |
|---|---|---|
| 原有四个强化浏览器用例 | PASS，四项均通过 | `ui-20260920-013742-499.log` / `.xml`；`ui-e2e/20260920-013743/` |
| 第五例：书目补齐、计划展示、刷新保留、实际编译交付 | PASS，修正测试换行断言后 13.43 秒 | `ui-20260920-013940-823-bibliography.log` / `.xml`；`ui-e2e/20260920-013941/` |
| 真实 Windows XeLaTeX、PDF、源码 ZIP、全部物理页 PNG | PASS（上述成功流程的明确断言） | 实际下载文件并核对 PDF/PNG 签名、ZIP 内容；第五例为 4 页 |
| FDU 适配摘要及产物 | PASS | 第一轮第二例核对计划可见、刷新后保留，ZIP 内使用 `fduclassroom` |
| 真实 API 未配置时的 UI 提示 | PASS，仅隔离测试环境 | `ui-e2e/20260920-013743/live-unconfigured.png`；测试切回 MOCK 后才提交 |
| 真实 API | NOT_RUN（本 UI 回归） | 子进程主动关闭 live、清空 API key；不表示用户 Windows 环境未配置 |
| 教师数学与逐页视觉验收 | NOT_RUN | 成功任务停在 `AWAITING_USER_REVIEW`，没有人工审核记录 |
| 三章完整输入矩阵、Windows 启停脚本 | 本轮 UI 回归未运行 | 由相应专项报告认定，不能由本次小 TeX fixture 推断 |

本报告这一阶段是**四项通过加第五项定向复测通过**，当时没有一次全部五项同时通过的记录；后续最终全五例结果见上方链接。首次五项运行的原始结果为 **4 passed, 1 failed，52.89 秒**；失败记录原样保留。

## 新增书目路径的断言

使用合成的小 TeX（只引用 `BradyWeil`，不预填书目），以及本地真实 `大学数学（一）(1).tex`：

1. 书目补齐 checkbox 默认未勾选，完整原稿存在时可用；测试明确勾选后才创建任务，模型选择为 MOCK。
2. 计划中默认展开“从完整原稿补齐的书目与出处（本次确认范围）”，检查 `BradyWeil`、完整原稿文件名、原上传与原稿哈希、条目哈希及书名均可见。
3. 独立核对条目正文为完整原稿对应字符区间的原文，哈希相同；出处位于原稿第 12424 行，来源区间结束于 12425 行。没有网络补造条目。
4. 原上传字节、原始快照与测试上传文件完全一致；派生源码位于另一个目录并含补齐条目。浏览器刷新后原计划 hash、补齐选项和 provenance 完整保留。
5. 确认、执行、再次刷新后，任务实际到达 `AWAITING_USER_REVIEW`；编译和忠实度报告均 PASS，实际 PDF、源码 ZIP、4 张物理页 PNG 都能下载。导出源码仍含引用及原条目正文，交付的 `plan.json` 仍含相同 provenance。
6. 完成后再核对原上传、原快照、完整原稿未变；`reviews` 为空。完整原稿 SHA-256：`f73bb3c88540f4470ddf08881622cb014ee2904c4a03f551ad06fe2a1db7cb8d`。

机器可读记录：`ui-e2e/20260920-013941/bibliography-verification.json`。计划截图为同目录的 `bibliography-plan.png`，最终页面截图为 `test_reference_bibliography_opt_in_preserves_sources.png`。两轮所有浏览器控制台错误记录均为空。

## 命令与隔离

在工程根目录执行下列测试，实际日志和 JUnit 路径如上表。证据目录通过当前进程环境指定；运行结束后恢复原环境值。

```powershell
$env:MATH_AGENT_E2E_EVIDENCE_ROOT = Join-Path (Get-Location) 'reports\iteration2\ui-e2e'
.\.venv\Scripts\python.exe -m pytest tests/e2e/test_browser_workflows.py `
  -m e2e --basetemp workspace\t\2e9b52b4 `
  --junitxml reports\iteration2\ui-20260920-013742-499.xml -q -ra

# 修正仅影响末尾换行的测试断言后，只复测失败用例。
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -m pytest `
  tests/e2e/test_browser_workflows.py::test_reference_bibliography_opt_in_preserves_sources `
  -m e2e --basetemp workspace\t\e980e68a `
  --junitxml reports\iteration2\ui-20260920-013940-823-bibliography.xml -q -ra
```

以上 basetemp 目录是已保留的证据，不应重复使用；后续复测请使用新的短目录。测试 fixture 从子进程环境移除所有继承的 `MATH_AGENT_*`，再设置独立 workspace/reference root、`MATH_AGENT_LIVE_API_ENABLED=false` 和空 API key。端口由本地临时绑定分配，分别是 53742 与 62289；fixture 仅停止自己创建的服务和 worker。复测结束后对这两个端口的本地连接均返回 Windows `10061`（连接被拒绝），确认测试服务已停止。

工作区及数据库、编译日志、PDF、PNG、源码都保留于 `workspace/t/2e9b52b4/` 和 `workspace/t/e980e68a/`。每轮的 `context.json`、server/worker 日志、Playwright trace ZIP、截图及控制台记录位于对应 `ui-e2e` 目录。测试没有读取或记录用户密钥；本轮用户环境及真实 API 验证应以 root 的独立记录为准。

## 保留的失败与局限

- 首次 `py_compile` 写入 `__pycache__` 被受限执行环境拒绝，返回 `Permission denied`，没有声称该命令通过。后续经工具授权执行 pytest，实际加载并运行同一文件。
- 首轮第五例已经通过计划、刷新、原件保护、真实编译/PDF/ZIP/全页 PNG 检查，随后因 `raw_tex` 的 CRLF 与 Windows 导出文件末尾换行不同而失败。只读核对确认条目正文存在；测试改为只去掉期望条目末尾的 `\r`/`\n`，正文仍逐字核对。未修改产品、未放宽编译或质量门禁，原失败日志和产物未删除。
- 此次合成 fixture 只验证一条真实来源的书目补齐路径，不代表三章全部引文、复杂排版或数学语义已经审核。
- README 启动命令与 UI/脚本入口一致；其中旧“本机未配置真实 API”等状态文案已通知 root 按本轮事实更新，本子任务未编辑 README。
