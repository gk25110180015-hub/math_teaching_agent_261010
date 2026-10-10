# CH01 S03 新增练习答案复核

2026-09-19T19:41:59.664Z。Run：`05748ab6260c40989a560a98e1e2065a`。

**U16、U17的追加答案正确回应题设；原17个单元和原2个计算请求完整保留，检查点确为补齐后的19单元版本。整章仍PENDING_OUTPUT，教师验收NOT_RUN。**

本次只读，0 API；没有修改数据库、正文或实现，没有新编译或页面视觉验收。

## 追加内容与保真

- 原17个unit完整对象及顺序逐字一致；新增 `S03.U16.answer`、`S03.U17.answer`，kind均solution，分别精确关联U16、U17。
- 原2项calculations完整保留；另追加C03，关联U17.answer，核算根式极限1/2。
- 原calculation_limitations保留，另追加一条说明“具体极限不核验全称不等式证明”；uncertainties未变。
- 初始section哈希：`7dbd0e0f1f4cf3ac3f713477ed9e9adc9e1c13e2d2fb34202ddd70f04a54e02e`。
- 补齐后section哈希：`6e5e8c24f9761326a9a9cfab675fdc3c67822a864f11dd5fd804f9d77240db13`。两者与答案补丁证据一致。

因此“原请求未改”成立，但“整个calculation列表没有变化”不成立，实际为2→3项。

## 两份答案的数学核对

### CH01-S03-U16

题目 S03.U16，答案 S03.U16.answer。n为正整数保证n+1>0，|sin n|≤1给出|b_n|≤1/(n+1)≤1/n，双侧±1/n均趋0，夹逼得0。答案没有未经证明断言sin n收敛，也没有把有界当作收敛；说明乘积法则要两因子均收敛，而本题无需这一条件。

全体正整数上的界、上界趋0的理由、不能直接相乘的解释均齐全。

### CH01-S03-U17A

题目 S03.U17，答案 S03.U17.answer。正整数n使共轭分母正且sqrt(n²+n)=n sqrt(1+1/n)，原式=1/(sqrt(1+1/n)+1)。再由0≤sqrt(1+1/n)−1=(1/n)/(sqrt(1+1/n)+1)≤1/(2n)直接夹逼，根式趋1，分母趋2≠0，极限1/2。没有偷用函数连续性。

### CH01-S03-U17B

题目 S03.U17，答案 S03.U17.answer。原式减2精确为[(-1)^n−2]/(n²+1)，n²+1>0。绝对误差≤3/(n²+1)≤3/n²→0，故极限2；不需要(-1)^n收敛。

## 实际检查点与编译

SQLite只读section.S03记录的output_hash为 `1e8cb75a494959efc5358a9ad36ad4a8719873e3d4ebbe19e187da1ce2f3f2e9`，payload哈希一致；generated完整等于补齐后的候选。source_hash `d858786506f43cb8644f46a368cc95e1f16c25d6bc8652231dfe9b3b1c86333c` 与实际编译源一致；引用检查PASS、无pending_labels。

补丁应用时证据仍写APPLIED_UNCHECKED/NOT_RUN，这是当时不可变记录；后续review-1和数据库检查点已实际完成数学/编译，不能把旧补丁状态误读为当前未检查，也未修改它来伪装通过。

既有Windows XeLaTeX编译PASS、2遍、7页，指S01+S02+S03累积稿。PDF SHA-256 `5be03a87daeeb6eacce883737938e55fbc07c13ff55f6b81cbe5f3bdb753d682` 已与文件核验。本次未重编译。

新增答案在编译源的定位：U16题L290、U17题L299、U16.answer L326、U17.answer L338；适用于报告所列源码哈希。

## 核算与验收层次

本机真实SymPy重跑三个AST，结果为0、3/2、1/2。独立再核对 sin(n)/(n+1)→0、sqrt(n²+n)−n→1/2、振荡误差界3/(n²+1)→0及正负符号支路均→2。没有API或mock。

这些程序核算是具体表达式证据；正整数定义域、共轭合法性、∀n不等式和不偷用连续性由AI文本审读确认，不是形式化证明。人工页面/教师验收NOT_RUN；本次不评整章最终覆盖。

## 证据文件

| 文件 | SHA-256 |
|---|---|
| [candidate-normalized.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS03_9352d2ae9887/candidate-normalized.json) | `c6a0071f3fbb8cb18c19e06c938816b5fe65edfad02eca34e2d70d62d42d644d` |
| [answer-repair-1-candidate.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS03_9352d2ae9887/answer-repair-1-candidate.json) | `ab01b3b863f5769c6746bf960b4d91ae908a24fa6ff1bb08e0fd49e446db873a` |
| [answer-repair-1-evidence.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS03_9352d2ae9887/answer-repair-1-evidence.json) | `342f9e90d6c7020f1768f8e4bd514809634596c96ec6f79a8f9f7fc7937f448a` |
| [answer-repair-1-normalization.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS03_9352d2ae9887/answer-repair-1-normalization.json) | `7e9d9219257ee0b0ad3ff730b57c304267cd6de0d1ca2897f3f808fcebd84406` |
| [review-0.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS03_9352d2ae9887/review-0.json) | `17a6f813f68cd1e7ec6a1471b9d06d17418c8b0a2595861e1d1dbf2310468358` |
| [review-1.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS03_9352d2ae9887/review-1.json) | `5feed62a4b577402563a43548f97f6bff566a78696a155fbb489b06da2f79b6f` |
| [compile.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS03_9352d2ae9887/compile.json) | `cac6207c3673e258d8109b336074ba9264a2dc3fc4496c1baf90120f98410271` |
| [source/lecture.tex](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS03_9352d2ae9887/source/lecture.tex) | `d858786506f43cb8644f46a368cc95e1f16c25d6bc8652231dfe9b3b1c86333c` |
| [build/lecture.pdf](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS03_9352d2ae9887/build/lecture.pdf) | `5be03a87daeeb6eacce883737938e55fbc07c13ff55f6b81cbe5f3bdb753d682` |

