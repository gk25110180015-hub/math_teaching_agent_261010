# 2026-09-26 用户 QUALITY_BLOCKED 修复

目标：修复网页上传第四章 TeX 转 Beamer 的失败，并检查讲义工作流的共同问题。

- 原任务：`e53fd34585fb4bc9af2a85fd994d610a`；原构建 job：`ccd8a766f61c454b931dd8fadb98c371`。
- 原状态：BLOCKED，compile.global，第 3 次构建。失败原因为 U0116/U0123 图中文字 `\scriptsize` 被 B-16 拦截；尚未编译。
- 原文件、原审批、旧产物未覆盖。`before/agent.db` 是 SQLite 一致快照，`before/baseline.json` 保存原审批与 51 个已有文件哈希；修改前代码亦在 before。
- 已修：仅适配命名字号；列表 leftmargin 布局选项；嵌套证明/解答及列表后续正文的完整步骤拆页；合法字号下的第二排版候选；共用错误摘要、质量 Markdown 具体问题及网页可读诊断。
- 不放宽任意缩放或未知字号门禁，不删除数学内容；报告 presentation_adaptations.json 保留来源位置和改动；原稿和锁定计划不变。
- 修复前字号用例 11 FAILED，日志保留；第一次新增拆页回归出现 1 FAILED/49 PASSED（自定义列表），已修复；之后针对性 52 PASSED。
- 隔离 `workspace/q0926/p1` 至 p4 均保留，p1/p2 暴露后续列表/溢出，p3 出现源区间空白缺口，已修复。
- p4：实际 Windows XeLaTeX PASS，来源保真 PASS，209 页均渲染；没有 blocking PDF 几何问题，仍为 NEEDS_REVIEW（字体替代、版面边界提示）。此隔离转换没有模型 API 请求。
- agent 查看 p4 的 21 页：19、20、34、35、36、70、71、110—117、132、140、152、206—208。检查缩略图位于 visual。未发现这些页原有越页裁切；图中文字提高到 footnotesize 后图示标签布局仍由教师复核。不是教师验收，未查看其他全部页面。
- 第一次完整测试 full.log 和 edge.log 因会话额度/执行中断而不完整，没有 XML 结果，不能称为通过。原日志未覆盖。
- 2026-09-26 17:15 恢复执行 `full-resumed.*`：1119 PASSED / 16 FAILED / 15 deselected。16 个失败是 mock 测试继承本机流式/备用模型环境造成的分支差异。直接 pytest 命令也选中了 real_api 标记：`test_live_provider_opt_in` 实际执行“只回复 OK。”连通探针，2.912 秒 PASS；其默认回调未保存最终路由和尝试数，不能推断三个模型分别通过，也不是实际教学生成验收。
- `edge-resumed.*`：实际 Edge 6 PASSED，mock 模型、真实 Windows 编译，教师复核 NOT_RUN。
- 已按既有隔离入口 `scripts/run_iteration4_regression.py --run` 重跑全部本地测试，证据 `reports/iteration4/local-full-20260926-172116-e8575839.*`；显式排除 real_api/e2e，测试进程清除模型环境，用户环境未改变。
- 该隔离轮实际为 1132 PASSED / 2 FAILED / 1 real_api deselected；两个失败为数学子进程未完成检查，未更改为 PASS。直接复现的完整结果在 `math-investigation.json`，复現时符号极限 PASS、数值抽查 numeric_spotcheck_passed 且整项 NEEDS_REVIEW（抽查不是证明）。原失败日志未包含子进程具体证据，不能推断原因。
- 给上述两条断言补充实际结果作为失败信息，不改变条件；17:27 再次隔离全套，证据 `reports/iteration4/local-full-20260926-172749-629dc90e.*`。需要读取最终结果，不可提前宣布通过。
- 剩余：读取最终测试结果；更新证据报告；启动已部署本地服务；通过原任务 retry 恢复原 job；检查审批/旧文件/请求计数不变；验证网页下载及源码包干净编译。不要 POST 人工 reviews，也不要发起无关模型调用。

人工教师数学验收 NOT_RUN；人工教师视觉验收 NOT_RUN。Beamer 恢复不需要模型请求；整轮实际 API 执行情况按上面的连通探针记录，不能误记为全未运行。

## 最终完成记录（2026-09-26）

- 上面的“剩余”清单现已完成。最终隔离回归 `local-full-20260926-172749-629dc90e.*` 为 1134 PASS、0 FAILED、0 ERROR、0 SKIP；1 项 real_api deselected；21 项 Windows 编译标记用例包含预期失败/取消情形；源码快照稳定。
- 8765 默认服务和 8766 历史三章服务已重启到修复版本，worker 正常。不要重复启动。
- 原 job 已通过应用 retry 恢复为 attempt 4 / done；任务为 AWAITING_USER_REVIEW，209 页。原审批 revision 2、输入、51 个旧文件哈希及 0 次请求计数保持不变，未提交 reviews。
- `production-recovery.json` PASS：227 个下载文件哈希正确；源码 ZIP 在 `workspace/q0926/delivery` 实际重编译 PASS，209 页全文逐页一致。不要再次执行 recover_and_verify.py --resume。
- 实际 Edge 辅助核验的 Invalid URL 和同名草稿定位失败保留于 production-ui 至 production-ui3。production-ui4 PASS；最终 production-ui5 PASS，核验本次构建五种下载及哈希，展开 20/132/140/208 页、验证图片加载并截图，agent 已查看。无页面错误、无修改请求、无教师审核。
- `RESULT.md` 已记录完整结果与局限。第 132 页图示标签仍需教师检查；不宣称全 209 页已由人工验收。
- 此 bug 修复、部署、原任务恢复和自动验收已完成。用户刷新 http://127.0.0.1:8765 后选择“第四章导数.tex”即可继续逐页复核与下载。
