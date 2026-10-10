# CH01 S05：AMS text 数学作用域误拒诊断

结论：本次 `LECTURE_FRAGMENT_AMBIGUOUS / Mixed math delimiters` 是解析器误判。原候选和首个被拒 strict patch 的 S05.U02 都包含合法结构：外层显示数学中的 array 单元使用 `\text{$\varepsilon$--$N$ 定义}`，AMS `\text` 参数进入独立文本模式，内部可以再进入行内数学。原单一 math_mode 错把这些 `$` 当成外层 `\[...\]` 的混合定界符。

最小修复只处理已知 `\text` 的平衡花括号参数：递归独立校验其中的数学定界符，保留参数全部字节，深度上限 24。真正混用、未闭合参数、错配数学、文本内教学环境、未知宏作用域仍阻塞。归一化证据版本为 4，未修改任何数学内容、核算请求、源资料或被拒提案。

真实 S05 整节重新归一化后的 base SHA 仍为 `6f31ff52e79f09979fcea606449134c07e7dec008989920ed7a030ff81867463`，与已有 local-repair 身份完全相同，无需猜选候选、迁移正文或清除计数。原 candidate、patch、normalization 及 S05 状态字节 SHA 均核对未变，见 `text_math_scope/diagnosis.json`。拒绝记录仍保留；本修复没有将旧拒绝响应改判采纳。

恢复审阅身份同时增加 `deterministic_checks_hash`：包含本轮模型审阅前的完整确定性问题、引用检查、归一化 checker version/status/issues。正文 SHA 和数学核算 SHA 仍独立保留。归一化转换前的原文坐标、变换历史及局部 subset 元数据不作为“新证据”，避免无内容变化的补丁清空旧疑点。测试证明旧 parser FAIL → 新 PASS 可带着原疑点明确重评，而完全相同内容/实际检查结果下的随机空审阅仍不能清除已记录问题。

执行证据：

| 日志 / XML | 结果与含义 |
|---|---|
| `text-math-before` | 8 FAIL、6 PASS、1 deselected；先红测试复现合法 AMS 文本作用域被误拒，保留日志。 |
| `text-math-after` | 98 PASS、1 FAIL；旧外壳、方程标签、中文标点和恢复回归通过，含 4 项实际 Windows 编译。唯一失败为新编译 fixture 缺少 plan.provider，尚未调用该项编译器，不是产品编译成功。 |
| `text-math-final` | 修正 fixture 后 37 PASS，15.58s；包含 2 项实际 Windows 编译。 |
| `text-math-review-identity` | 5 PASS、16 deselected，1.75s；确认确定性检查变化与无效/no-op 补丁后的审阅身份边界。 |

实际 U02 捕获表格正文逐字不变，经受控 `LECTURE_HEADER/render_lecture` 和 Windows XeLaTeX 编译得到 **PASS、1 页、issues=[]**。稳定证据位于 `text_math_scope/probe-source`、`probe-build` 与 `probe-evidence.json`。宽表 OVERFULL 门禁保持原样，测试没有放宽阈值或过滤编译问题。

这些执行全部显式空 API key、LIVE=false、STREAMING=false。本次 **真实 API NOT_RUN、教师视觉/教学验收 NOT_RUN**，不表示 S05 其他数学疑点已解决，也不表示该节已获正式验收。当前真实 driver 已载入的旧代码不会热更新；后续重试由主任务在完整回归后决定。
