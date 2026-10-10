# M2：讲义、真实适配器与数学检查

实现环境变量设置、CompatibleChatProvider/MockProvider、版本化 planner/writer/reviewer/repair 提示词、严格 JSON/Pydantic 及业务验证、有限结构修复/网络重试、总超时、请求预算与脱敏。准确请求用户指定的 `/v1/chat/completions`，模型标识 `gpt-6-astra`；无可选 schema/tools/vision 假设。

讲义按节生成，检查必需类型、题解/证明关系和决策；SymPy 仅执行有界 JSON AST，独立无密钥子进程。局部编译通常须成功；仅计划预登记的后续标签可标PENDING_FULL_REFERENCE_CHECK并保存待全文验证的检查点，原编译FAIL日志保持不变，未知引用/缺书目不能豁免。全文必须全部解析，并复核实际单元与相邻节依赖、检查重复内容，最后编译/全页渲染。Mock 输出明确为离线合成示范；没有假装按任意专题完成真实教学内容。

证据：`M2_offline.log` 当时 59 passed / 11 deselected；`compiler_math_validation.md` 记录 Windows、符号未知、量词/定义域、错误级数与数值证据边界；`crossrefs_validation.log`含实际前后节引用及aux编号核对。最后汇总以`FINAL_ACCEPTANCE.md`指向的JUnit为准，不把不同阶段的重复测试累加成新通过数。

真实 API：**BLOCKED / NOT_RUN**。`real_api_condition.log` 实际执行条件用例并 1 skipped，原因是新密钥环境变量和 live 开关缺失；`provider check --live` 返回 PROVIDER_NOT_CONFIGURED。没有使用聊天中的密钥，也未向供应商发起真实教学请求。

因此 M2 的真实模型端到端完成条件未满足。用新的环境密钥显式启用后先运行 provider check，再创建小型 live 讲义；模型/价格/图像能力以实际返回为准。数学工具不是通用证明器，未支持的核算列为 NOT_RUN/UNKNOWN；自定义比例等语义落实须人工核对质量报告。
