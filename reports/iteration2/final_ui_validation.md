# 第二轮最终五例浏览器回归

执行时间：2026-09-20 02:24:10（Asia/Shanghai）。**5 passed in 55.40s；0 failed、0 errors、0 skipped。** 本轮在全局定向修复、方程标签与 Service/lecture CRLF 修正稳定后的代码快照上执行，全部五例一次通过。后续定向修改须由其对应验证单独认定。

这是实际 Edge + 独立 FastAPI/worker + SQLite + 本机 Windows XeLaTeX 的 UI 回归。模型供应商全部 MOCK；所有继承的 `MATH_AGENT_*` 从测试子进程移除，再显式设定 `MATH_AGENT_LIVE_API_ENABLED=false`、空 `MATH_AGENT_API_KEY`、`MATH_AGENT_LLM_STREAMING=false`。没有导入 Windows User 环境，没有 API 调用，不影响用户的真实 API 配置。

| 用例 | 实际关键断言 |
|---|---|
| 讲义生成、确认与刷新恢复 | 自定义为每题末项、默认未代选；保存决策、改标题、确认、执行和刷新；最终待人工复核；实际 PDF、源码 ZIP、全部页 PNG 可下载 |
| Beamer 精确删除与新增 | 真实 FDU；模板适配摘要可见且刷新保留；实际例题及关联题解按授权删除、新内容加入；输出 TeX 和 fidelity PASS |
| 自定义计划效果 | 自定义文字进入计划并在刷新后保留 |
| 真实编译失败与重试 | 实际编译 FAIL 含 `UNDEFINED_CONTROL_SEQUENCE`、状态包含 `QUALITY_BLOCKED`；错误报告可下载；重试后不返回重复确认 |
| 完整原稿书目补齐 | checkbox 默认关闭、显式开启；原条目/出处/哈希展示，刷新与交付计划保留；原 upload、快照和完整原稿字节未变；实际编译/fidelity PASS、4页 PNG/PDF/ZIP；教师 review 为空 |

成功路径明确要求最终 `AWAITING_USER_REVIEW`，不会把任意离开队列或失败状态当通过。所有成功路径逐个下载 `.page-review` 中的 PNG 并检查签名，同时下载 PDF 检查签名、读取 ZIP 并检查实际源码与禁带文件。五份 `*-console.json` 全为 `[]`。

实际命令（日志由执行端同时捕获，以下短临时目录已保留，不应复用）：

```powershell
$env:MATH_AGENT_E2E_EVIDENCE_ROOT = Join-Path (Get-Location) 'reports\iteration2\ui-final-e2e'
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -m pytest tests/e2e/test_browser_workflows.py `
  -m e2e --basetemp workspace\t\1ff660a7 `
  --junitxml reports\iteration2\final-ui-20260920-022409-905.xml -q -ra
```

执行结束恢复了父进程原证据目录和输出编码环境值。测试 fixture 仅清理自己创建的服务/worker。独立端口为 `57364`，结束后 `Get-NetTCPConnection -LocalPort 57364 -State Listen` 返回0个监听；未启动、停止或修改 8765/8766 服务。

- [完整日志](final-ui-20260920-022409-905.log)
- [JUnit](final-ui-20260920-022409-905.xml)
- [运行上下文](ui-final-e2e/20260920-022410/context.json)
- [书目核验 JSON](ui-final-e2e/20260920-022410/bibliography-verification.json)
- [截图、trace、console 与 server/worker 日志目录](ui-final-e2e/20260920-022410/)
- 持久数据库、输入及全部编译产物：`workspace/t/1ff660a7/`。

`live-unconfigured.png` 只反映本轮主动隔离的测试环境，不表示用户当前 Windows User API 变量缺失。教师数学/逐页视觉验收 **NOT_RUN**；模型真实 API **NOT_RUN（本 UI 测试）**。本轮不重新认定三章全量质量或脚本真实服务启动。

先前书目新增测试的 `4 passed, 1 failed` 与后续定向 `1 passed` 原样保留，见 [此前记录](ui_validation.md)。本次没有删除失败日志，没有降低编译、来源或人工审核门禁。
