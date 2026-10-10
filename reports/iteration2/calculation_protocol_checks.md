# Writer 数学核算协议验收

新增 `src/math_agent/calculation_protocol.py` 的 `calculation_protocol()`，返回独立可JSON序列化数据，供根pipeline注入context。提供完整支持kind/AST/布尔假设白名单、变量和实际unit_id绑定、8秒单项预算、无法核算与数值证据的保守解释。

实际命令：`.venv\Scripts\python.exe -m pytest tests/test_calculation_protocol.py -q -p no:cacheprovider`。

实现前先出现模块不存在的collection error；实现后 **7 passed in 10.56s**。测试没有mock核算器，实际启动现有mathcheck隔离子进程调用SymPy；不是模型API测试或Windows TeX编译测试。

- `lim(1/n,n→+∞)=0`，正整数假设：symbolic_check_passed。
- `Σ(n=1..∞)1/n²` 收敛性：symbolic_check_passed；未声称核算级数和。
- `d(log(x))/dx=1/x`，正实定义域：symbolic_check_passed。
- 移除对数正定义域：not_checked / NEEDS_REVIEW，有domain_requirements。
- 未声明所需变量：not_checked / NEEDS_REVIEW。
- 仅两个点的数值抽查：numeric_spotcheck_passed，同时NUMERIC_IS_NOT_PROOF / NEEDS_REVIEW。

writer提示已要求1至3个与实际本节内容相关的支持请求，确实无适用操作则`calculations=[]`并写`calculation_limitations`。真正数学疑点继续写`uncertainties`，不能用工具限制字段掩盖。TeX只写单元正文，不重复kind外层环境，并明确JSON反斜杠转义。

真实API：本子任务NOT_RUN；PDF/Windows TeX/教师视觉：本子任务不适用。根任务负责协议context注入与计算问题定位、完整API工作流。
