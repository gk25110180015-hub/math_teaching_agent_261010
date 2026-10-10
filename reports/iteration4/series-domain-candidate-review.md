# 级数定义域检查候选：已离线验证，尚未合入生产

2026-09-20。本次只写新增测试、报告与待合并补丁，**未改运行中的 src、数据库、原始资料或旧讲义产物**。真实 API 请求 0，Windows 编译 NOT_RUN，教师数学/视觉验收 NOT_RUN。

## 已复现的漏洞

现 `mathcheck._calculate` 直接使用 `SymPy.Sum(...).is_convergent()`。实际 SymPy 1.14.0 对 `sum(1/(n log n), n=1..∞)` 在预期 `expected_convergent=false` 时返回 PASS，而 n=1 项无定义；从 n=2 起则合法发散。尾部收敛判断本身不能证明整条级数的每一项均有定义。

首版候选仅检查首项，主任务指出 `1/(n-2)` 从 1 起首项有限、第二项无定义。该边界也已真实复现：生产版本将其及消去前有同样分母的表达式视为通过。首版只检查首项的候选已经被更保守版本取代，旧文件按内容 hash 归档，没有声称其可作最终检查。

## 候选行为

1. 在受限 JSON AST 转换过程中保留原负幂分母、实对数正值、平方根非负和 tan 的 cos 非零约束，避免 SymPy 简化/约分先消掉定义域问题。
2. 先检查确定整数起点的原表达式约束。确定无定义返回 FAIL / `series_term_undefined`，参数或起点不能确认返回 UNKNOWN，不由尾部收敛结果放行。
3. 再以 `n=start+k`（k 为非负整数）代入所保留的约束及有限实值条件。SymPy 不能证明约束对该尾段成立则返回 UNKNOWN，并列出约束；例如从 1 起的 `1/(n-2)`、`(n-2)/(n-2)` 和 `sqrt(2-n)` 不会 PASS。从 2 起 `1/(n log n)`、从 2 起 `1/(n-1)`、p=2 级数等正常对照保留正确收敛结果。
4. 这是受支持运算的保守域检查，不是通用定义域证明器。有限和/复杂函数可能更保守地 UNKNOWN；不通过数值抽样推定所有项有定义。成功与未知证据都带 `domain_scope=supported_tail_guards` 和限制说明。
5. 正文没有通用 TeX→数学 AST。另加 80 余行有界记号扫描，只识别显式整数起点、无穷上限、整数分子、分母为可选指标正整数幂乘以 ln/log 指标的正整数幂；不执行宏、不解析任意代数表达式。只返回 `SERIES_FIRST_TERM_DOMAIN_REVIEW` / review，含单元 ID、字符 span、变量和起点，不自动改正文或直接 blocking。
6. 正文扫描先遮蔽注释、verbatim 和字面 `iffalse`。显式“错误示例/误写/错式”等前置语境或紧邻“首项无定义”等后置说明不作为正确陈述报错；正确从 2 起的公式旁说明错误起点 1 不误报。该语境识别仍是启发式，不能保证理解全部错误辨析措辞；生僻语法与宏保留为未覆盖范围，而非数学 PASS。

## 补丁与测试文件

先合并 [series-domain.patch](待合并/series-domain.patch)（结构化 AST），再合并 [series-text-domain.patch](待合并/series-text-domain.patch)（新正文扫描模块与 `_static_checks` 接线）。两者合并后的预览为 [mathcheck-series-domain.py](待合并/mathcheck-series-domain.py)，新模块为 [series_domain_text.py](待合并/series_domain_text.py)。[SHA 记录](待合并/series-domain-source-hashes.json)包含基底和候选 hash；基底 `mathcheck.py` 的 SHA 为 `654c101490de5db5eb4febce0c29391838777ba674503a02f07429c26aeeac70`。

新增生产回归用例已放在 [test_series_start_domain.py](../../tests/test_series_start_domain.py) 和 [test_series_text_domain.py](../../tests/test_series_text_domain.py)。合并前直接对生产实现运行会出现预期红测，不能纳入“完整回归已经通过”声明。候选验证通过独立 Python 进程内模块替换，未将候选复制到 src；AST 用真实 SymPy，正文为确定性本地扫描，两者均无网络。

| 实际执行 | 结果 | 证据 |
|---|---|---|
| 初版生产实现首项/证据契约回归 | 15 FAILED（6 个未定义反例及新增范围契约等）；不是应用修复后结果 | [日志](series-domain-red.log)、[XML](series-domain-red.xml) |
| 仅首项的初版隔离候选 | 15 PASS；已被更保守候选取代，不代表后续极点已检查 | [日志](series-domain-candidate.log)、[XML](series-domain-candidate.xml) |
| 生产实现后续极点/失域边界 | 3 FAILED，14 deselected | [日志](series-domain-later-pole-red.log)、[XML](series-domain-later-pole-red.xml) |
| 改进后的 AST 隔离候选 | 17 PASS | [日志](series-domain-candidate-v2.log)、[XML](series-domain-candidate-v2.xml) |
| 生产实现正文扫描回归 | 7 FAILED，15 PASS | [日志](series-text-domain-red.log)、[XML](series-text-domain-red.xml) |
| 最终 AST + 正文扫描隔离候选 | **39 PASS，0.64 秒** | [日志](series-domain-candidate-v3.log)、[XML](series-domain-candidate-v3.xml) |
| 真实已保存 S03 候选只读重扫 | **仅 U13 被精确定位为 review**；U14 从 2 起的正确解答不报；旧候选与生产源码 SHA 未变 | [机器证据](series-domain-saved-unit-candidate.json) |

上述专项相互重叠，不相加为唯一用例总数。没有运行合并后全套应用测试、真实子进程集成、API、Windows 编译或教师验收；它们应由主任务合并后分别执行。

## 和缓存/恢复的衔接

新增检查不会仅凭新源码自动让旧 CHECKED S03 失效。主任务需通过正常检查契约/恢复工作流重新核查旧正文，将 U13 的定位意见送入有证据的局部修订，并保留先前编译稿和全部账本。候选没有按 CH02、S03 或 U13 硬编码；真实单元只用于额外回归证据。检查契约应包含 `mathcheck.py` 与新增 `series_domain_text.py` 的变化，不能仍复用旧数学 PASS。
