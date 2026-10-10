# 真实应用只读 UI 验证与侧栏修复

最终四案例的自动 UI 检查 **PASS**，61/61 个真实产物或部分文件 HTTP GET / SHA256 检查通过。第二、三章仍为 **BLOCKED**，全文交付 **NOT_RUN**；所有案例的教师审核均 **NOT_RUN**。界面检查通过不代表完整数学讲义通过或教师批准。

| 案例 | 实际工作流状态 | 请求数 / 上限 | 文件 GET / SHA | 实际部分章节 | 最终证据 |
| --- | --- | --- | --- | --- | --- |
| smoke | AWAITING_USER_REVIEW | 21 / 60 | 21 / 21，含全部 5 PNG | 不适用 | [报告](ready-css-v3/smoke/result.json) |
| CH01 | AWAITING_USER_REVIEW | 37 / 60 | 25 / 25，含全部 11 PNG | 不适用 | [报告](ready-css-v3/CH01/result.json) |
| CH02 | BLOCKED / BUDGET_EXHAUSTED | 33 / 60 | 9 / 9：PDF、TeX、checkpoint | 3 / 5 | [报告](blocked-css-v2/CH02/result.json) |
| CH03 | BLOCKED / BUDGET_EXHAUSTED | 27 / 60 | 6 / 6：PDF、TeX、checkpoint | 2 / 5 | [报告](blocked-css-v2/CH03/result.json) |

Microsoft Edge headless 在实际 `http://127.0.0.1:8766`、`workspace/iteration2-live` 上运行。最终记录的 189 个浏览器/API 请求全为同源 GET，无外部或状态修改请求。所有 case 均检查刷新后恢复同一 run、真实 API 标记、状态及链接，前后 budget/count/审批/reviews/失败/job/产物保持一致；reviews 始终为空。界面及 API 在此次运行中显示每单元修复有效上限 2、全文修复有效轮数 2，预算版本均为 0；这项观察不代表每个任务都持久化了这两个初始字段。没有扩额、重试、教师审核、模型调用或服务启停，8766 留给用户继续使用。

最终只读数据库审计补充：smoke 原始预算行仅持久化 `requests=60`，`local_repairs_per_unit` 与 `global_repair_rounds` 为 **UNRECORDED**；上述显示值 2 来自当前服务的有效配置，不能回填或声称其历史初值已经记录。CH01、CH02、CH03 的 60/2/2 均已实际持久化。原始 UI 快照保留所见值，JSON 汇总已加来源说明。依据：[最终运行与状态核验](../final-runtime-and-state-20260920-051655-382274-verified.json)。此次仅更正报告表述，没有写数据库或重新运行检查。

完整交付路径下载了所有公布产物，包括所有 PNG，并保存 PDF 与源码 ZIP，核对 ZIP CRC/TeX 成员；实际加载首末页预览。阻塞路径逐个下载可用 checkpoint PDF/TeX/JSON，核对服务器 PARTIAL 标记、公布哈希和下载字节哈希；界面保留“全文未完成”“部分结果待复核”和 UNKNOWN 计划关联说明，不据此猜测旧检查点已经绑定当前计划。

实际执行命令如下，各目录均为新建：

```powershell
.\.venv\Scripts\python.exe -B scripts/verify_live_delivery_ui.py --base-url http://127.0.0.1:8766 --case smoke --case CH01 --output reports/iteration2/live-ui-final-20260920-050656/ready-css-v3
.\.venv\Scripts\python.exe -B scripts/verify_live_blocked_ui.py --base-url http://127.0.0.1:8766 --case CH02 --case CH03 --output reports/iteration2/live-ui-final-20260920-050656/blocked-css-v2
```

首次 `ready/` 记录了脚本断言失败：关闭的 HTML details 导致 `inner_text` 读取不到隐藏页哈希，46 个文件下载哈希当时均通过。只修验证脚本为读取前展开该页后，`ready-v2/` 功能检查通过。但 agent 查看实际截图发现侧栏长专题按钮越界覆盖主内容，此问题完整保留于 [原始截图](ready-v2/CH01/overview.png) 和 [修复前汇总](summary.json)。这次没有把功能 PASS 当作视觉 PASS。

待最后全量测试与后置 SHA 采集完成、root 授权后，仅对 `style.css` 追加桌面侧栏最小约束：grid 使用 `minmax(0,1fr)`，相关元素允许 `min-width:0`，按钮 `max-width:100%`；移动端规则与业务逻辑、DOM、测试文件未改。原 CSS 保存在 [style-before.css](style-before.css)。前 SHA `b0b98eef36cb693cca078fff2906c399110b613be77090eada42682038706ef2`；后 SHA `6c99e09a1e15d96bfba39b06df69ab12c7c76df9b5415fd8159b7638c1c87fd2`。

随后四案例重新执行所有功能/下载/状态不变检查，并加入实际长标题边界断言：1440×1100 视口中侧栏右边 260px，四个按钮最右均为 241px；列表 scrollWidth/clientWidth 都为 223px。真实标题自然宽度为 962–1097px，受限显示省略号。agent 查看 [修复后 CH01](ready-css-v3/CH01/overview.png)、[CH03 阻塞界面](blocked-css-v2/CH03/blocked-overview.png)、[实际侧栏](blocked-css-v2/CH02/sidebar.png)，确认此前遮挡已消除。这是 agent UI 视觉检查，不是教师逐页数学验收。

全量后端证据 [local-final-20260920-050545](../local-final-20260920-050545.json) 的 546 PASS 对应 CSS 修复前的快照。对其 110 个记录文件逐项复核，随后仅 `src/math_agent/web/static/style.css` 改变；不声称 546 项覆盖修改后的 CSS，也未因这处样式调整重复后端全量。最终真实 Edge 验证覆盖该 CSS，脚本与源快照边界见 [summary-after-css.json](summary-after-css.json)。

所有首轮失败、修复前视觉发现、后续通过记录、console/page errors、网络请求、截图和下载字节均保留。ready 的控制台只有 Edge 惰性加载图像的信息提示；无 pageerror；blocked 控制台为空。
