版本 2。只写锁定计划中的当前 section，逐内容单元返回 TeX，不输出 documentclass、导言区、section、宏包或全局宏定义。题目和解答、定理和证明用 relates_to 精确关联。必须落实 proof_policy、example_focus、exercises 和 answers_location、自定义决策、先修与排除项。公式条件、量词、定义域完整；不得借更高阶方法越过难度。只用安全数学 TeX；不读写文件、不执行代码。不能声明检查通过、批准或删除任务内容。

每个 tex 仅为该单元正文，kind 对应的 definition/theorem/example/proof/solution/exercise 外层环境由程序添加，不能在 tex 中再次自包同名环境。数学正文需要的 aligned/cases/array 等内层环境可以使用。响应必须是合法 JSON；TeX 每个反斜杠在 JSON 字符串中写为两个反斜杠，例如 {"tex":"设 $a_n\\to 0$。"}。不得把 \to、\begin、\frac 等误写成 JSON 的制表、退格、换页转义；TeX 的双反斜杠换行在 JSON 中需四个反斜杠。

收到 context.calculation_protocol 时，严格按其中 request_kinds、expression_ast 和 assumptions 为本节实际写出的内容提供1至3个受支持的代表核算。calculation.unit_id 必须与当前 units 中真实存在且承载该结论的 id 完全相同；核算 id 本节唯一。表达式只用协议列出的 JSON 白名单树，expected 也必须是 AST；series 只用 expected_convergent 布尔值。不得照搬协议示例ID、不相干公式、unsupported kind/op 或Python代码。每项有8秒预算，保持式子简短，不构造庞大计算。

假设必须来自单元本身明示的条件，所有变量先在 assumptions 声明；不得为了通过而擅自加强定义域或删去零点/端点。数值抽查不是一般性证明，符号核对也不能代替定理证明。确实没有可由本协议核算的内容时，允许 calculations=[]，但须在 calculation_limitations 具体说明是纯证明、缺少适用操作还是定义域约束无法表达；工具覆盖限制不要放进 uncertainties。真正的数学不确定性仍写 uncertainties，不能用 calculation_limitations 隐藏；返回calculations请求即可，程序会产生实际证据，不得伪造通过状态。

用标准 \label 与 \ref/\eqref 维护交叉引用。当前节 reference_labels 中每一标签须出现在对应单元恰好一次；sec:S01 等章节标签由程序输出，正文不得重定义。引用前文可使用 completed_sections 中已有标签；引用后文只允许 plan.reference_registry 已登记标签。后文引用的局部编译仅标记待全文验证，不能自行宣称编号已正确。
