# 2026-09-27 删除计划与连贯分页

用户最新任务 0d14ccca52404f7585446dc6f9535ef9，第四章导数.tex。
只读核查：已保存 U0001/U0002 删除授权，但 sections 仍列 U0002，导致空 S02 及目录残留。
旧分页先 split，再全章 separate_units，产生不必要拆页。

before 目录保存原代码、最新任务输入/计划、一致性 DB 备份；原任务尚未修改。
新增 beamer_scope.py：有效计划排除已删内容和空节，source_sections 保留可恢复来源清单。
新增 beamer_layout.py：连贯组先 normalsize/small/footnotesize 实际编译，溢出组才语义拆分；保留未溢出组。
render_beamer 增加 frame 日志标记，完整 overlay 测量；保真检查仍按精确来源区间。

待完成：针对性回归、最新真实材料的独立编译比较、实际 Edge 删除/恢复/交付测试、完整隔离回归、部署及交付。
本轮真实 API NOT_RUN；教师数学与视觉验收 NOT_RUN。不得覆盖原任务审批或假冒人工 reviews。

## 部署进度

最终代码完整隔离回归：reports/iteration4/local-full-20260927-011231-30904cc6.*，1144 PASS / 0 FAIL / 0 ERROR / 0 SKIP，1 real_api deselected，21 Windows 编译标记用例，源码稳定。
p2 最终真实编译/保真 PASS：134 logical frames、178 physical pages；44/58 关联题解同 frame，正文 normalsize 52 / small 12 / footnotesize 66；无 blocking 几何或页脚风险提示。20 页最终抽查已查看，仍非教师验收。
8765/8766 已部署重启且健康。最新原任务已通过 /recheck 入队，使用原审批及原删除授权，不重写计划哈希。恢复任务和下载验证由 recheck_and_verify.py 进行；production.json 保存 job_id。若会话中断，读取并等待原 job，不要再次运行 --execute 或重新 POST。
最后待办：确认 production.json（包含原文件/审批保留及 ZIP 干净编译）结果；运行 verify_ui.py；更新 RESULT/README 和最终只读核验。

## 已完成

上述部署待办均完成。production.json PASS：原 job 35f15deb895d4193a0f4ae6ef58850bc 完成，原计划及审批不变，452 个旧产物未变，202 个新下载逐一验 hash；完整源码 ZIP 在干净目录编译 PASS，178 页文本逐页一致。
edge-final.xml：最终版 7 PASS。production-ui/report.json：真实已部署原任务只读 Edge PASS，有效 4 节、178 个预览、4 类下载、4 页图片正常，无页面错误、无修改请求。
用户刷新 8765 后查看最新“第四章导数.tex”，状态仍为 AWAITING_USER_REVIEW。本次修复、部署、原任务重建和自动测试已完成；教师审核始终 NOT_RUN。
