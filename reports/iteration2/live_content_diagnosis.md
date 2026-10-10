# 真实 smoke 内容与教学诊断

读取对象：run `426866cf71d2437bb17b54ac801a8c18`，已批准 plan revision 2、hash `9e57a417de22ea8854850c2e7554dbb6603347d7547f552813e76f6cca122a2d`；首节原始候选 `workspace/iteration2-live/b/426866cf71d2437b/sS01_219c4aaaa7f6/candidate.json` 及同目录 `review-0.json`。本诊断未调用 API，未改写原候选，不是教师教学／视觉验收，也不是形式化证明。

## 已确认的实质问题

| 类型 | 单元／证据 | 判断与影响 |
|---|---|---|
| 确定的渲染缺陷 | U01 definition、U02 theorem、U03 proof、U04 example、U06 exercise 均自带完整环境；renderer 又按 kind 包环境 | 产生重复编号、重复定理／证明标题或 QED；不能依靠 schema-valid 认定可交付 |
| 确定的编译缺陷 | S01-U05、S01-U07 含 `\\begin{solution}`；读取时受控 LECTURE_HEADER 没有定义 solution 环境 | 需要修复内容片段边界；数学解法正确也不能覆盖编译失败 |
| 核算协议没有送达模型 | 原 WrittenSection 的 calculations 仅为 `list[dict]`；writer 提示“已约定 JSON 白名单树（不认识协议则留空）”，实际 schema 未列 op／kind／assumptions 协议 | 候选 calculations=[]；实际 check_math 为 NEEDS_REVIEW，evidence 为 NOT_RUN。同模型审阅无问题不能替代独立符号复算 |
| 局部审阅范围错位 | `review-0.json` 的唯一 blocking 指向 `unit_id=S02`，理由是输入只有 S01-U01…U07，未提供未来 S02 | S01 局部门禁不应要求第二节已经生成。须显式限定 local section scope，并校验审阅 issue ID 属于实际已送单元；不能为解除该误报而删除真实问题或假造第二节已检查 |

这些都是生成和检查接口的问题，不是依据与原讲义文字不同而判数学错误。

## 数学、先修和教学安排核对

- **S01-U01（定义）**：明确实数数列、正整数下标、A 为实数；量词顺序为任意 ε>0、存在正整数 N、所有 n>N。环境后的说明明确 N 可依赖 ε，不能随正在检验的 n 改变。这一段是定义的重要解释，剥除外壳时必须完整保留。
- **S01-U02／U03（唯一性与证明）**：假设同一实数数列收敛于 A、B，反设不等后取 ε=|A−B|/3，分别取得 N1、N2，再取 n>max(N1,N2)，由三角不等式导出矛盾。该推理在已读正文中完整，未发现确定错误；不能因此推断未读第二节正确。
- **S01-U04／U05（例题 1/n→0）**：任意给 ε，选择正整数 N>1/ε，对所有 n>N 得 1/n<1/N<ε，正确。floor(1/ε)+1 是合法具体取法，但 floor 符号不在计划先修／符号表中；本科初学者最好补一句“向下取整”或只保留足够大的整数阈值。正整数无上界／阿基米德性质是隐含基础，宜明确提示，而非新增高阶定理课程。
- **S01-U06／U07（练习 2+3/n→2）**：误差为 3/n，取 N>3/ε 的验证正确，答案显式关联到 U06。练习主要是原例的常数缩放和平移，适合作为本次最小 smoke 的近迁移练习；不能据一题声称完整章节的练习层次或经济学应用已验收。
- **先修**：计划顶层列实数、绝对值不等式、正整数数列、分式化简、基础量词；S01 无内部先修，S02 仅依赖 S01，顺序闭合。S01 证明没有使用函数极限、导数或其他排除内容。三角不等式依赖已列的绝对值基础。
- **S02 计划（尚不能替代实际正文）**：明确商法则要求分母极限非零、由此分母最终非零、有限初项不影响极限；计划覆盖这些条件是正向证据，必须等实际生成正文和证明后再核查落实。
- **选择与答案位置**：实际锁定选择为 key／balanced／with_answers／end。U05 关联例题，应该留在正文；U07 关联练习，应该移至末尾。本次 Windows fixture 已检查源 TeX 中 U05 位于“练习答案”之前、U07 位于之后，但这仍不等于教师逐页视觉确认。

## 确定性外壳修复的独立验证

新模块 `src/math_agent/lecture_fragments.py` 提供 `normalize_written_section(data) -> (normalized, evidence)`。只移除一个顶层、与 kind 相同的教学环境外壳；保留普通数学环境、全部 ID／relates_to、正文和环境外解释；可选标题以原文 `\\textbf{标题}\\par` 保留。嵌套／多重教学环境、kind 不匹配、括号／环境／数学分隔符不平衡都保持原文并返回 BLOCKED，不盲目剥除。

证据包括原始／归一化整节及逐单元 hash、移除字符区间、保留的前缀／正文／后缀 hash。首节候选文件 SHA-256 为 `c10c9320d90cd25c8868673fb6468857812159951dd1c18034cc4f64f8907f94`；规范化 JSON 原始 hash 为 `f542f1993cb94d9c1b26979885f29217e66c003dda572cf76957547b718254e1`，外壳处理后为 `7f11719eda6684b1db73d5ec488bec1216e3b0e8fe8b94e5ed07498897426b73`。此函数不是安全预检、数学核验或教师验收；root pipeline 负责接入并处理 BLOCKED。

先红测试日志：`lecture_fragments_red.log`。离线测试 **16 passed, 1 deselected**，日志 `lecture_fragments_unit.log`。真实首节 fixture 的 Windows 测试 **1 passed, 16 deselected in 4.47s**，日志 `lecture_fragments_windows.log`。

实际使用该首节原始候选、当前受控 render_lecture／LECTURE_HEADER、绝对 XeLaTeX 引擎编译两轮，结果 compile PASS；各教学环境数量恰好对应各 kind 单元数，没有 solution 未定义。归一化证据、TeX、PDF、每轮日志与 compile_result.json 保存在 `workspace/lecture_fragments_windows_01/test_actual_live_first_section0/`。仍有 Fandol 粗斜体字体替代 review，未声称版式或教师验收通过。此次局部编译没有发送新 API 请求。

## 基准比较指标的补足

仅比较单元数量和页密度不足以揭示本次问题。benchmark 新增 `draft_candidate_diagnostics` 与 `checked_section_pedagogy`：区分初稿和通过检查的正文，列出重复外壳候选、计划必需类型缺失、题解关联、结构化计算请求数量／指向单元／显式假设缺失。`calculations=[]` 显示 NOT_RUN；存在请求仅显示 REQUESTED_NOT_VERIFIED，必须另读对应实际 math 证据。

指标测试先失败后实现，红日志 `benchmark_pedagogy_red.log`；完整 **13 passed in 0.56s**，日志 `benchmark_offline_tests.log`。所有统计比较仍为 NEEDS_REVIEW；初稿风险不得冒充修复后最终缺陷，统计不能升级教师 PASS。

教师人工视觉验收：**NOT_RUN**。正式教学验收：**NOT_RUN**。
