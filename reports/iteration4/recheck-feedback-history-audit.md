# 带全局修复历史的反馈复检审查

结论：在本次只读代码审查和四项追加 mock 集成测试中，**没有发现旧全章通过结论绕过当前 job 反馈的路径**。生产源码、冻结候选与提示词均未修改。

审查对象是 [Pipeline 冻结候选](recheck-feedback-pipeline.candidate.py)，raw SHA `43058915b1775a9236d0a98732aa8131c4f2eecddbdf09802a14d7ad14b34695`，以及与其放在同一隔离包的四份 API/UI 候选。不是对正在运行的 CH03 数据库作突变测试。

## 代码路径核对

- **LocalRecovery CHECKED / 全局 validated**：`lecture()` 的 validated 分支只允许复用合法节检查点，仍调用 `_global_interfaces(completed, plan)`，没有直接返回旧 global PASS 的路径。完整实际正文到达全章审阅后，重新按事件读取当前反馈。
- **已有 rounds_used**：旧轮次不归零。validated 的历史轮次已达上限时，正式新复检仍先审阅新反馈；如果新审阅确认缺口，才记录新失败并以预算不足阻断。没有把未修好结果发布为通过。
- **global repair_pending**：真正失败/阻塞状态不允许正式 `/recheck`，该接口只接受 AWAITING_USER_REVIEW。应通过原 job 的 `/retry` 恢复已确认的问题；重试先完成保存的限定单元修复和局部检查，再用当前 job 反馈审阅实际新正文。不能用空反馈消除已核实、未解决的数学问题。
- **最新空反馈撤回**：完成前轮后，再提交同批准计划的新正式空反馈动作，会生成新 job。读取最新匹配计划事件后返回无反馈，不向后捡起早先非空意见；已经接受的正确修复和累计轮次仍保留。
- **审阅证据**：每次反馈全章请求前写独立 feedback 文件，正文单元哈希按本轮实际内容计算；响应由原 review_units 保存。修前和修后均有独立审阅，原 failure 会归档。来源事件不转为教师记录或新计划授权。

“一定审阅”有明确边界：只有执行成功走到全章检查时才发生。若更早因局部检查、相邻接口、模型连接、证据校验或耗尽状态阻塞，就不能声称本轮反馈已审阅。此时任务不完成，原动作与失败证据保留，不能把这类诚实阻塞称为旧通过缓存绕过。

## 追加的真实状态路径 mock 测试

[tests/test_recheck_feedback_history.py](../../tests/test_recheck_feedback_history.py) 使用真实临时 SQLite、正式 TestClient `/recheck`、Service 的增额与重试规则，模型和编译器全部为 mock。模拟调用逐次计入真实请求账本，并核对最后计数等于模拟调用次数；不把次数复位为零。

| 路径 | 检查结果 |
|---|---|
| 历史因额度 1 阻塞，正式增额至 6，原 job 恢复后已有 2 轮 validated；新正式反馈触发第 3 轮并再次审阅 | PASS |
| 上述第 3 轮完成后最新空字符串 / 空白字符串撤回反馈，整章仍审阅，但不再传旧意见；轮次仍为 3 | PASS（两个参数） |
| 第 3 轮模型修复调用中断，保持 repair_pending；直接 recheck 被拒；原 job retry 修复后全章使用同一反馈事件和修后正文 | PASS |
| 历史 2 轮已用尽；新正式反馈先审阅再明确 budget_exhausted，显式增额后先修保存问题，再审实际新正文 | PASS |

实际是 **4 个 pytest 节点通过，5.08 秒**：第一、二行共同由两个参数节点验证，另两行各一个节点。生产五文件前后 SHA 不变。[最终日志](recheck-feedback-history-03.log) / [JUnit](recheck-feedback-history-03.xml)。此次只跑新历史路径，没有重复前次 46 项简单集成测试。

前两次运行各为 3 FAIL / 1 PASS，均为新增测试的预算初始化错误，不是产品反馈缺陷：第一次在等待复核时企图增额，被合法 BUDGET_NOT_BLOCKED 拒绝；第二次给 Settings 传入超过启动默认上限的 6，被合法校验拒绝。最终测试改为完整真实“先阻塞→显式增额→原 job 重试”初始化，没有放宽产品规则。[首次日志](recheck-feedback-history.log) / [第二次日志](recheck-feedback-history-02.log) 已保留。

本次 **真实模型 API、Windows XeLaTeX、PDF 视觉、教师数学/视觉均 NOT_RUN**。没有发现需要新增生产补丁的真实 bug；当前候选继续保持冻结。最终完整套件仍应动态收集这个新增测试文件。
