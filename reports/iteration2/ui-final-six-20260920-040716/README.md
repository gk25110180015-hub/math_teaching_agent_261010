# 最终冻结代码：6 项浏览器整合复测

2026-09-20 实际执行结果：**6 PASS，79.12 秒**。完整命令、耗时与源码身份见 [summary.json](summary.json)，[pytest.log](pytest.log)、[JUnit](junit.xml) 保留原始结果。

这轮覆盖原有 5 个完整工作流用例及新增的显式预算恢复用例。使用真实 Edge headless、独立临时 FastAPI/worker、真实 Windows XeLaTeX/渲染/下载，provider 全部为 **mock**；子进程密钥为空、live/streaming false。真实 API 测试 **NOT_RUN**，教师数学/视觉审核 **NOT_RUN**。真实讲义任务及 8765/8766 均未触碰。

测试目录：`workspace/t/u6f01`。两套 module fixture 分别建立独立随机端口并自行清理；实际端口关闭校验、逐用例结果和 6 份空的 JavaScript pageerror 记录见 [cleanup-and-cases.json](cleanup-and-cases.json)。

## 覆盖范围

1. 讲义交互：真实 API 未配置标识、结构化问题/推荐值、计划标题修改、确认、刷新恢复、执行、真实 PDF/ZIP/所有 PNG。
2. Beamer：精确源单元删除、用户新增内容、FDU 主题适配说明、计划审批与实际产物。
3. 结构化问题的自定义输入：保存为计划中的具体效果，刷新后仍可见。
4. 编译失败：实际错误及保留报告，不把任意终态算作成功。
5. 显式书目补齐：默认不勾选、来源证据在计划可见、刷新保持、真实编译。
6. 请求预算耗尽：合成计数触发真实 Store 门禁，展示已保存章节，6 个部分文件的 HTTP/SHA 校验；用户从 120 明确调为 121 后保持 BLOCKED，原计数/审批/错误/jobs/artifacts/reviews 不变；刷新后用户另点重试，真实编译回 `AWAITING_USER_REVIEW`，核对新 PDF/ZIP/全部 PNG 及所有新增 artifact 的 HTTP/SHA。合成的 120 次计数没有发出 120 次模型请求。

具体用例名和结果以 JUnit 为准；测试没有提交教师审核。浏览器截图、trace、服务器/worker 日志分别在 [原有 5 例](browser/20260920-040754/) 与 [预算恢复](browser/20260920-040847/)。预算结构化结果见 [budget-flow-evidence.json](browser/20260920-040847/budget-flow-evidence.json)。

## 源码冻结证明

对 `src/`、`tests/`、`prompts/`、`templates/`（排除 pycache）和 `pyproject.toml`/`uv.lock` 共 **102 个文件**逐字节计算 SHA-256。测试前后全部一致，新增/删除/修改文件均为 0：[source-before.json](source-before.json)、[source-after.json](source-after.json)。本次未为通过测试修改产品代码或测试。

预算专项早期 fixture 错误和失败产物仍保留，说明见 [budget_validation.md](../budget_validation.md)。本轮六例首次执行全部通过，不覆盖或改写早期记录。
