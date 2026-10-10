# 第二轮新增全稿审计

本审计只读取用户资料并写入报告，未调用真实 API，未执行教师视觉验收。

全稿 TeX：`D:\研究生阶段\数学教学agent\大学数学（一）(1).tex`，435,670 字节，12,441 行；SHA-256 `f73bb3c88540f4470ddf08881622cb014ee2904c4a03f551ad06fe2a1db7cb8d`。
配套 PDF：144 页；SHA-256 `b754d756826f406fb3b5c55851af1d1f8a21a286d629771477e632e91f6e7423`。这里只读取页数，未将已有 PDF 视作本轮新编译通过。

## 结构和完整性

| 章节 | 标题 | 原文行范围 |
|---|---|---|
| 1 | 数列与数列极限 | 235—1486 |
| 2 | 无穷级数 | 1486—2138 |
| 3 | 函数极限与连续性 | 2138—3714 |
| 4 | 导数的概念与计算 | 3714—6249 |
| 5 | 导数的应用 | 6249—7717 |
| 6 | 不定积分 | 7717—8723 |
| 7 | 定积分与二重积分 | 8723—11325 |
| 8 | 常微分方程初步 | 11325—12414 |

另有不编号的“数学文化与数学史导引”。稿尾共有17个真实书目条目；全稿正文所有静态引用键均有条目，未检测到外置 input/include/image/bib 依赖。TikZ 图形内嵌于源码；TeX宏包与字体仍依赖本机TeX安装。

## 与既有三章关系

| 样本 | 新旧正文差异 | 补全条目 |
|---|---|---|
| CH01 数列与数列极限 | trim后完全相同 | BradyWeil |
| CH02 无穷级数 | 仅末尾新增一个 clearpage；数学内容相同 | NCBISteadyState |
| CH03 函数极限与连续性 | 仅末尾新增一个 clearpage；数学内容相同 | NCBIEnzyme, BradyWeil |

这三组仍可与原手工 Beamer 基准比较。新稿补齐的是原三章遗漏的真实书目依赖，没有改变数学正文。各条目的原始内容、行号、字符区间和SHA-256均写入JSON。书目信息未另行联网核实；不能把“原稿有此条目”等同于已核对出版信息。

原三章 51 份已登记资料全部重新校验，51 份哈希未变。

原文习题标题仍写“第2/3/4章”，而正式section计数对应1/2/3，属于原稿编号一致性问题，保留并披露，不私自改写。

## 可复用实现

`math_agent.manuscript.complete_bibliography`只复制正文实际引用的缺失条目，已有条目不覆盖，未知键仍阻塞，重名冲突显式报告。`extract_chapter`保留原导言区、原章号、完整章正文（含原先不显示的答案分支）并附所需条目。`write_prepared_copy`使用独占新文件和来源sidecar，拒绝覆盖任何文件。

应用应在计划中披露该补充及其来源哈希，用户审批后使用独立derived副本，原始上传快照保留。章节提取副本的跨章引用仍需真实编译，不能仅靠提取成功声称可发布。

复现审计：`.venv\Scripts\python.exe reports/iteration2/audit_source.py`。模块命令：`python -m math_agent.manuscript audit/extract/supplement --help`。

## 比较指标

- Source fidelity：check_fidelity parses actual emitted TeX against exact source units; omissions need explicit confirmed IDs。
- Citation completeness：Count missing active citation keys before/after supplemental bibliography, require compiler UNRESOLVED_REFERENCE zero after full passes。
- Build success：Real Windows XeLaTeX, both default/FDU templates, keep prior failed logs and compare exact blocking rule IDs。
- All-page geometry and overlays：Render every physical page, compare blocking geometry separately from review-only contacts and human ratings。
- Density/readability：Compare logical frames, physical pages, supported font sizes and content per frame with original manual Beamer; page-count reduction alone is not quality。
- Generated lecture mathematics：Use fixed topic/scope/decisions, source proposition coverage, explicit assumptions, proof completeness, bounded CAS where applicable, plus independent teacher review。
- Training/validation separation：These are local style/reference examples; no model weight fine-tuning, no blind held-out accuracy claim; chapters4-8 may supply unseen-topic probes only after scope selection。

三章是本地参考样例；本轮不等于模型权重训练。任何真实API、Windows编译、自动几何与教师评分应分开列证据，不用单一“通过率”掩盖未执行项。
