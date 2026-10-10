"""Serializable writer-facing contract for the existing bounded JSON-AST checker.

This is documentation/data, not another calculator or an expression evaluator.
Every example is exercised against the actual mathcheck subprocess in tests.
"""
from __future__ import annotations


def calculation_protocol() -> dict:
    """Return a fresh JSON-compatible protocol suitable for model context."""
    def integer(value):
        return {"op":"Integer","value":value}

    def symbol(name):
        return {"op":"Symbol","name":name}

    def power(base,exponent):
        return {"op":"Pow","args":[base,integer(exponent)]}

    return {
        "schema_version":1,
        "purpose":"为本节已实际写出的数学结论提交1至3个受支持的代表性核算；核算不是对整节内容的证明。",
        "output_field":"calculations",
        "limitations_output_field":"calculation_limitations",
        "uncertainties_output_field":"uncertainties",
        "selection_rules":[
            "unit_id必须精确等于当前返回units中真实存在且包含该结论的id；id是本节唯一的核算ID。示例ID仅用于演示，不能直接借用。",
            "只复算本节实际出现且符合课程范围的式子，不为凑1至3项新增例题、升级难度或虚构结论。",
            "确无适用核算时返回calculations=[]，并在calculation_limitations说明具体覆盖限制；真正数学疑点另外保留在uncertainties。",
            "只填写请求，不能在请求中增加status、evidence或通过结论；程序运行后才产生证据。",
        ],
        "request_common_fields":{
            "required":["id","unit_id","kind","assumptions"],
            "id":"本节唯一字符串，例如S01.C01",
            "unit_id":"当前units中的实际ID，例如S01.U04；结论、变量、预期结果须与该单元一致",
            "assumptions":"符号名到白名单布尔假设的对象；所有Symbol和variable都必须声明。常量式可用{}。",
            "extra_fields_allowed":False,
        },
        "request_kinds":{
            "equivalence":{"required":["lhs","rhs"],"ast_fields":["lhs","rhs"]},
            "derivative":{"required":["expression","variable","expected"],"ast_fields":["expression","expected"],"variable":"已在assumptions声明的符号名字符串"},
            "limit":{"required":["expression","variable","point","direction","expected"],"ast_fields":["expression","point","expected"],"variable":"已声明的符号名字符串","direction_values":["+","-","+-"],"direction_note":"有限点+为右极限、-为左极限、+-为双侧；示例的正无穷极限使用-。"},
            "series":{"required":["term","variable","start","end","expected_convergent"],"ast_fields":["term","start","end"],"variable":"已声明的求和符号名字符串","expected_convergent":"JSON布尔值，只核对收敛性；此kind不核对级数和"},
            "numeric_spotcheck":{"required":["lhs","rhs","points"],"ast_fields":["lhs","rhs"],"points":"1至20个对象，每个对象覆盖所有声明变量；值为有限JSON数，绝对值不超过10^9，且满足声明假设","warning":"仅有限指定点数值一致，不能证明一般结论；返回numeric_spotcheck_passed仍需复核。"},
        },
        "assumptions":{
            "symbol_name_pattern":"[A-Za-z][A-Za-z0-9_]{0,30}",
            "allowed_boolean_flags":["real","positive","negative","nonnegative","nonpositive","integer","nonzero","finite","rational"],
            "rules":[
                "布尔值必须是真正的JSON true/false，不能写字符串、集合、区间或Python表达式。未明确的属性不要写false，保留未声明。",
                "假设来自单元明示条件，不得为了得到PASS而擅自加强条件。实对数参数为正；含倒数的恒等变形需保留非零条件；根号求导需检查正值区间与边界。",
                "白名单不能表达的一般区间/复合约束必须说明限制，不能用更弱或更强的单一布尔属性冒充。系统的域检查不完整，仍须核对原结论条件。",
            ],
        },
        "expression_ast":{
            "encoding":"表达式只能是以下JSON对象树，不接受TeX、数学字符串或Python代码；所有节点不允许额外字段。",
            "nodes":{
                "Integer":{"keys":["op","value"],"value":"JSON整数，绝对值<=10^9；不能用布尔值或小数"},
                "Rational":{"keys":["op","p","q"],"p_q":"有界JSON整数，q不为0；小数尽量写精确有理数"},
                "Symbol":{"keys":["op","name"],"name":"assumptions已声明的符号名"},
                "Infinity":{"keys":["op"],"meaning":"正无穷；负无穷可用Mul(Integer(-1),Infinity)的JSON树"},
                "Add":{"keys":["op","args"],"arity":"1..16"},
                "Mul":{"keys":["op","args"],"arity":"1..16"},
                "Pow":{"keys":["op","args"],"arity":2,"note":"第二项为指数AST；数值指数绝对值<=100"},
                "sin":{"keys":["op","args"],"arity":1},
                "cos":{"keys":["op","args"],"arity":1},
                "tan":{"keys":["op","args"],"arity":1},
                "exp":{"keys":["op","args"],"arity":1},
                "log":{"keys":["op","args"],"arity":1,"note":"自然对数，检查正实定义域"},
                "sqrt":{"keys":["op","args"],"arity":1},
                "Abs":{"keys":["op","args"],"arity":1},
            },
            "syntax_notes":[
                "乘方用Pow；除以x用Mul(分子,Pow(x,Integer(-1)))；减法用Add(左式,Mul(Integer(-1),右式))，均展开成JSON对象树。",
                "不要发明Div、Subtract、Float、Limit、Sum、pi或Python等op/kind。初等常数e可写exp(Integer(1))；不支持的表达式留为覆盖限制。",
            ],
        },
        "budgets":{"per_calculation_timeout_seconds":8,"per_section_timeout_seconds":60,"max_request_utf8_bytes":65536,"max_ast_nodes":256,"max_ast_depth":20,"max_function_arguments":16,"max_declared_symbols":20,"recommended_requests_per_section":[1,3]},
        "evidence_interpretation":{
            "symbolic_check_passed":"只有所请求表达式在所声明假设下符号核对一致；不是一般定理的形式化证明，也不是整节审核通过。",
            "numeric_spotcheck_passed":"只通过所列点数值抽查，仍NEEDS_REVIEW，不是一般证明。",
            "symbolic_check_failed":"请求与核算结果冲突，属于须定位到原单元的数学问题。",
            "not_checked":"未执行、超时、域条件不完整或无法决定；不得视为PASS。",
        },
        "examples":[
            {
                "description":"数列1/n的正无穷极限；请求绑定实际含该结论的单元。",
                "unit":{"id":"EX_LIMIT.U1","kind":"explanation","tex":r"对正整数 $n$，数列 $a_n=1/n$ 满足 $\lim_{n\to\infty}a_n=0$。","relates_to":None},
                "calculation":{"id":"EX_LIMIT.C1","unit_id":"EX_LIMIT.U1","kind":"limit","assumptions":{"n":{"integer":True,"positive":True}},"expression":power(symbol("n"),-1),"variable":"n","point":{"op":"Infinity"},"direction":"-","expected":integer(0)},
                "expected_result":"0",
            },
            {
                "description":"正项p级数p=2的收敛性；此请求不声称计算其和。",
                "unit":{"id":"EX_SERIES.U1","kind":"explanation","tex":r"正项级数 $\sum_{n=1}^{\infty}1/n^2$ 收敛。","relates_to":None},
                "calculation":{"id":"EX_SERIES.C1","unit_id":"EX_SERIES.U1","kind":"series","assumptions":{"n":{"integer":True,"positive":True}},"term":power(symbol("n"),-2),"variable":"n","start":integer(1),"end":{"op":"Infinity"},"expected_convergent":True},
                "expected_result":True,
            },
            {
                "description":"在正实定义域内核对log(x)导数，不把公式外推到x<=0。",
                "unit":{"id":"EX_DERIVATIVE.U1","kind":"explanation","tex":r"在 $x>0$ 上，$f(x)=\ln x$ 的导数为 $f'(x)=1/x$。","relates_to":None},
                "calculation":{"id":"EX_DERIVATIVE.C1","unit_id":"EX_DERIVATIVE.U1","kind":"derivative","assumptions":{"x":{"real":True,"positive":True}},"expression":{"op":"log","args":[symbol("x")]},"variable":"x","expected":power(symbol("x"),-1)},
                "expected_result":"1/x",
            },
        ],
    }
