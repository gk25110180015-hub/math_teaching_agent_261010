# 部署后完整浏览器回归入口

`run_final_deployed_e2e.py` 已准备；**当前仅语法和 --help 验证通过，未执行新浏览器测试**。运行前先等待真实任务安全结束、统一合并反馈及其他候选，并冻结生产源码与测试。

```powershell
.\.venv\Scripts\python.exe reports/iteration4/run_final_deployed_e2e.py --run
```

脚本验证正式源码已包含反馈 API、支持范围门禁和 UI 后，再在唯一独立 `workspace/t/finaledge-*` 中运行全部 `tests/e2e`。预期 13 项：原 12 项，加反馈输入、轮询/重渲染/错误后保留及成功清空 1 项。未传 --run 或反馈未部署时不会开始测试。

进程环境移除真实模型密钥并禁用真实 API；模型选择 fixture 使用 dummy 凭据和 MockTransport。Edge 与讲义/Beamer 编译用本机真实浏览器、Windows TeX。程序保留 pytest stdout/stderr、JUnit、trace、截图、原测试工作区和每个 SQLite 快照，核实测试库 reviews 表与 human.review 事件均为 0。旧模型选择 fixture 写入的新 iteration3 目录会按文件哈希复制到本次 iteration4，不覆盖原证据。

每次输出 `reports/iteration4/final-deployed-e2e/<UTC戳>-<随机后缀>`。全量生产模块、静态文件、E2E 测试与 configs 在测试前后计算 SHA；须 13 项零失败、零跳过、源码不变、5 份模型选择证据完整以及所有测试库零人审，才汇总为 PASS。失败、超时或中断仍保留已产生的日志、DB 与产物；仅清理本脚本启动的测试进程树，不操作正式服务。

即使该回归通过，真实模型 API、教师数学及人工视觉验收仍不能据此宣称通过。
