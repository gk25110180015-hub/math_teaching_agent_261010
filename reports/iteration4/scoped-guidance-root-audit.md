# 定点修复联合候选审查

root 静态审查对象：`repair_guidance.candidate.py`、四处精确 Pipeline 编辑、API 三文件、UI 及各自候选测试。最终具体文件 SHA 以合并目录 manifest 为准；本文不是部署或真实数学验收声明。

API 在同一 SQLite 事务内核对原计划/审批、原 failed build job、当前候选语义和文件 SHA、实际目标单元及局部恢复绑定，记不可变建议事件并重排原 job。重复动作复用原 job；同 action_id 内容变化拒绝。既有预算拒绝会回滚新事件，没有增加审批、清零请求或绕过教师审核的入口。128 项离线 API 与旧接口测试在 `combined-recovery-validation/20260922-145813-9d3b56` 通过，生产未变、外网尝试 0；前轮两个错误码断言失败已保留。

helper 将建议作为明确的待核验输入传给既有 LocalPatch，只允许当前已有目标单元。普通数学问题、历史 uncertainties 和非目标正文/核算保留；没有实际正文或核算变化的提案拒绝，已保存的无效提案不会重抽。请求和按单元修复次数仍由原 provider/recovery 计数路径承担。接受标记先与局部恢复状态保存，随后同步全局候选；中断后在强制 seed 读取前补齐接受结果，避免旧全局候选盖回合法新正文。

已核实修正独审提出的全局目录冲突：新指针处于原 `round_directory` 内，原 `global_repair_contract.py` 不变。指导之前的 `recovery-before.json` 和可选 `global-before.json` 按原始字节保存，注册 dependency 的 SHA 必须与 action binding 相同；初始化中断的孤立文件只能按精确 SHA 接回，不可从已前移状态补造旧证据。该追加修改的实际测试以更新后的 helper manifest 为准。

Pipeline 仅四处接入：加载全局状态后的指导恢复、检查契约包含新 helper、待指导节不得直接采用旧完成缓存、局部合法候选恢复后应用指导，再进入原数学/疑点/编译链。合并脚本逐项精确替换比对，禁止整文件合并遗漏既有全局补丁约束。

UI 使用当前 run/plan/section/body 绑定的草稿及动作 ID。既有轮询修复保证 run 响应已到达时可先显示回执，不被尚未完成的 events 请求拖住。九项真实 Edge/模拟 API 测试只证明候选界面状态与请求行为，不能替代新部署全套 Edge、真实供应商或最终讲义验收。

本审查未发现需要放宽数学裁定或审批来完成恢复的理由。第二章须复验保存的原裁定；第三章原 `open_dependency` 必须保留，只有实际新正文补充可核验证明后才能重新裁定。新指导中的 Euler/有理参数证明路线已获独立审读，但建议本身不等于生成正文已实现，也不是教师通过。
