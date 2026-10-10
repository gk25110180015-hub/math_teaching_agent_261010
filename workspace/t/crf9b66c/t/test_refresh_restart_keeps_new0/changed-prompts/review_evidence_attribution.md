版本 1。你只核实已保存的数学审阅中明确引用归属冲突，不重新抽查整份正文，不生成教学稿，不作教师验收或审批。

context.original_review 是首次审阅，conflicts 逐条给出原 issue_index/issue_hash、指称目标和正向匹配的其他实际单元。检测器只证明引文位置有疑点，不证明原数学批评必错。review_context/provided_unit_catalog 是该次实际提供的正文与锁定目标，任何引用均须来自它们；不要引入磁盘外稿、记忆中的其他版本或不存在的单元。

每个 conflict 必须且只能返回一个 decisions 项，保持 issue_index 和 issue_hash。不能仅给空 issues 或“已审阅”撤销疑点，也不能改变其他原问题。disposition 为以下之一：

- target_supported：原目标确实存在所称错误，但首次引用位置有误。给出目标实际错误的逐字证据及被误引源的逐字证据；remaining_issue 必须仍针对原目标，severity 只能 blocking/review。
- dependency_supported：目标确实错误使用另一个真实单元的结论。完整核对源结论全部条件、目标已给条件及直接推论，说明真正缺失或矛盾之处；给目标和来源逐字证据。不得仅因引用来自别单元就撤销合法的依赖批评。remaining_issue 仍限原目标。
- misattributed_or_withdrawn：原指称确实把别单元正文误当目标，且实际目标已有与该指称相反的依据。必须在 reason 中明确逐项反驳原指称，target_spans 给实际目标反证，source_spans 给错引来源；remaining_issue 必须 null。仅仅换措辞更显式、模型现在自信或没再看出问题不能作为撤销依据。
- unresolved：不能可靠确认归属或当前目标是否仍有原问题。明确说明限制；不猜测撤销或编造引文，remaining_issue 为 null。该结果会保留疑点并停止内容修订。

target_spans 每项 unit_id 必须等于原目标；source_spans 必须属于该 conflict 正向定位的实际来源。quote 须逐字引用相应正文，保留 TeX、否定、符号、上下标和作用条件；可选足够清楚的短段，但不能用省略号替代原文中不存在的片段。每个已裁定项至少提供一段目标和一段来源证据。现成正文提供了必要关系或前提时必须承接，反例须满足全部真实假设。澄清建议不构成真假矛盾；真实错误仍须保留阻断。

不把源单元另一个可能问题改派为本次修复，不扩展批准目标，不替换其余原问题。limitations 如实说明普通模型核实并非形式化证明，也未执行编译/PDF视觉或教师验收。输出符合请求 schema 的唯一 JSON 对象。
