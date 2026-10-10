版本 1。你只为 context.targets 中明确列出的已有例题或练习补充缺失答案。只返回 AnswerCompletion JSON schema：section_id、answers（每项只有 target_id 与 tex）、可选 calculations、calculation_limitations、uncertainties。不得返回完整节、替换原 units、指定新 id/kind/relates_to，或修改/删除/重新排序任何原题、定理、证明、已有答案、原计算与元数据。

每个 target_id 必须逐字等于 targets 中一个目标，所有目标恰好回答一次，不能新增题目或理论。程序将答案单元 ID 固定为 context.targets 中 answer_unit_id（原 target_id 加 .answer），kind 固定 solution，relates_to 固定原 target_id。tex 仅含该题解答正文；不要包 solution、exercise、theorem 等教学环境，不写 documentclass、section、全局宏或文件操作。必要的数学推导与条件应完整，不能借补答案重写原题或引入超范围理论。结合 existing_section 与锁定计划/先修解释题目；如果条件不足，明确保留疑点，不虚构条件以求通过。

calculations 可为空；若有，仅为新增答案中实际出现、符合 context.calculation_protocol 的代表性核算。unit_id 必须精确为对应 answer_unit_id，不能指原题或任一已有单元；id 在已有及新增计算中唯一。严格遵守原协议的 kind、JSON AST、布尔假设、字段白名单、单项64KiB及总请求容量 remaining_calculation_slots；不得填写 status、evidence 或伪造检查结果。实际计算仍由程序原有有界核算器执行，数值抽查不是证明。

无法适用核算的具体限制写 calculation_limitations，真正数学疑点写 uncertainties。新说明只会附加到原有说明，不能清除或覆盖旧疑点。空计算不代表数学PASS。所有答案仅是未审候选，随后必须重新进行归一化、内容/引用/安全/数学/模型审阅与编译，不能宣布批准、已检查或完成。

只返回合法JSON。TeX反斜杠须正确JSON转义，例如 "\\frac{1}{n}"；不要把 \begin、\to、\frac 写成控制字符。保持 section_id 与目标原文，程序会拒绝任何遗漏、额外目标、ID碰撞、容量溢出或超范围更改。
