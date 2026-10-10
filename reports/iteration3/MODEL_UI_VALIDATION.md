# 三模型界面验证

新建真实 API 任务显示 `gpt6`、`deepseek-flash`、`deepseek-v4-pro` 三个选项，默认 `gpt6`。至少一个模型配置就绪时，界面默认选择真实 API；MOCK 仍为独立的离线方式。配置状态不表示即时 API 可用性已经通过测试。

任务页显示首选模型、最近实际尝试、最近通过结构校验的返回、已尝试模型、切换顺序和切换事件。已尝试列表包括失败请求；结构校验通过不表示数学审核通过。刷新保留后端的真实路由记录。旧任务无 `model_id` 时按 `gpt6` 展示，不修改旧输入或预算。

## 自动化浏览器验证

新增回归 **5 项通过，10.51 秒，0 跳过**：[日志](model-browser-20260920-1115.log)、[JUnit](model-browser-20260920-1115.xml)。测试实际开始时间由 JUnit 记录为 `2026-09-20T11:14:00+08:00`；文件名中的时间只作标识。

实际运行 Microsoft Edge、本机 FastAPI、SQLite、Worker 和 CompatibleChatProvider；供应商 HTTP 使用 `httpx.MockTransport`，输入为合成测试内容和无效测试凭据。**真实 API：NOT_RUN；Windows 编译：NOT_RUN；教师验收：NOT_RUN。** 8 个关键源码文件的测试前后哈希一致，见 [before](model-browser-20260920-1115-before.json) / [after](model-browser-20260920-1115-after.json)。

| 检查 | 结果 | 证据目录 |
| --- | --- | --- |
| 不触碰模型选择直接提交，默认为 gpt6；刷新恢复首选和实际调用 | PASS | [gpt6](model-selection-e2e/20260920-111401-deb947/evidence.json) |
| 选择 deepseek-flash，后端按该模型调用，刷新保持 | PASS | [flash](model-selection-e2e/20260920-111403-4f536c/evidence.json) |
| 选择 deepseek-v4-pro，后端按该模型调用，刷新保持 | PASS | [pro](model-selection-e2e/20260920-111405-af4b7e/evidence.json) |
| 模拟 gpt6 HTTP 504、flash HTTP 503，自动使用 pro 完成计划；3 次请求全部计数；首选仍为 gpt6；刷新保留 2 次切换 | PASS | [fallback](model-selection-e2e/20260920-111407-446269/evidence.json) |
| 切回 MOCK 后不调用三个真实模型 | PASS | [mock](model-selection-e2e/20260920-111409-a6c12c/evidence.json) |

两个 DeepSeek 选择用例均断言请求中 `thinking.type=enabled`、`reasoning_effort=high`、`stream=false`。用例没有提交计划确认、预算调整、任务重试或教师审核。所有页面 JavaScript 错误为空，浏览器外站请求为零。

Agent 已查看 [默认创建页](model-selection-e2e/20260920-111401-deb947/new-run-default.png) 和 [自动切换面板](model-selection-e2e/20260920-111407-446269/automatic-fallback.png)：文字可读，未见面板裁切或覆盖；这不是教师数学或视觉验收。

## 已保留的测试夹具失败

首次尝试中，测试直接在 Playwright 同步桥的线程内执行 Worker，触发 `asyncio.run() cannot be called from a running event loop`，实际模型 HTTP 请求为零。该轮中断，不能视为通过；[失败截图、trace 和证据](model-selection-e2e/20260920-111205-b1f1ea/evidence.json) 与第二个未完成用例目录 `model-selection-e2e/20260920-111240-6b25c4/`、隔离任务数据库 `workspace/t/b43d216e/` 保留。已将夹具改为独立线程调用 Worker，与产品独立 worker 的边界一致；没有为绕过夹具错误而修改产品 provider。

## 既有流程与最终部署界面

- 原有 **6 项工作流浏览器回归通过，85.83 秒，0 跳过**：[日志](existing-browser-20260920-1116.log)、[JUnit](existing-browser-20260920-1116.xml)。实际 Edge 与 Windows TeX 编译，模型为 MOCK；涵盖讲义、Beamer、原稿书目补齐、自定义计划、编译失败恢复及预算/部分稿交付。包含预期的编译失败场景，不能据“测试通过”称所有编译成功。8 个关键源码文件测试前后 SHA 一致；截图、trace、服务日志保存在 [工作流证据](existing-ui-regression/20260920-111516/context.json) 与 [预算回归证据](existing-ui-regression/20260920-111613/budget-flow-evidence.json)。真实 API 与教师验收均 NOT_RUN。
- 已部署主服务 `http://127.0.0.1:8765` 的只读 Edge 检查 **PASS**：[详细记录](model-ui-final-readonly-20260920-1120/report.json)。桌面 `1440×1100`、手机 `390×844` 均显示三模型，默认真实 API 与 gpt6；每种选择的后备顺序正确，无页面水平溢出、无 JavaScript 异常、无 POST、无模型调用。三个后端 profile 均显示已配置；该检查不再次验证供应商网络可用性。脚本为 `scripts/verify_model_selection_ui.py`。
- Agent 已实际查看最终 [桌面截图](model-ui-final-readonly-20260920-1120/desktop-model-choice.png) 和 [手机截图](model-ui-final-readonly-20260920-1120/mobile-model-choice.png)：模型选择和切换说明可读，未见遮挡；手机原生下拉框的长“真实 API”描述会按控件宽度显示，模型名称完整。教师验收仍为 NOT_RUN。
- 次服务 `http://127.0.0.1:8766` 仅 GET 读取配置和健康状态：[记录](model-ui-final-readonly-20260920-1120/secondary-runtime.json)。三项 profile 均已配置，worker 在线；未创建、恢复或修改任何旧任务、预算及人工审核。
