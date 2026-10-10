# 通用教学质量与恢复候选

## 合并交付

最终补丁是 `cached-teaching-quality-combined.patch`，完整候选是 `cached-teaching-quality-combined.candidate.py`，审阅提示词是 `reviewer_math_v5.candidate.md`。**最终补丁已包含之前的缓存契约修复，不应再重复应用 `cached-review-refresh.patch`。** 旧补丁、失败日志和初版候选均保留。

补丁只涉及 `src/math_agent/pipeline.py` 和 `src/math_agent/prompts/reviewer_math.md`。本子任务未修改这两个生产文件，未修改真实任务、预算、原稿、PDF 或用户审批，也没有发起 API 调用。合并时须与其他子任务的编译恢复/数学检查改动合并，不以完整候选覆盖他们的修改。

基线：

- pipeline SHA256：`350f9eff0d4a8f24937e4c0dfc605f7f2bb928fc603b313d99219553ea628a1c`
- reviewer v4 SHA256：`5d38a796ccdff81f3bba09d0c48210a836e83b77be5b31c2a814f7437e1ec69a`
- combined patch SHA256：`A52084DE70197C3BCAFD168EB0B50285C5686B7E5380805561F5DDBAFF314FD7`
- 完整 `.candidate.py` 的 raw SHA256：`6CF9B2400220458A1D94147CA7AE8ECFD655F3969A97CB918070DBA42C98F5C5`。这是运行 105 项验证时加载的文件，不能拿 `.patch` 指纹与它比较。

合并预检曾将补丁文件 SHA 与完整候选文件 SHA 比较，因此在写生产前停止。`combined-artifact-verification.json` 已分别列出两文件及日志指纹，并把候选逆向应用补丁后分别验证为冻结的 pipeline/reviewer 原始基线 SHA，结果 PASS。两者自 105 项测试前生成后未变；不存在“同一文件两个不同冻结指纹”的情况。

## 改进范围

原全章入口 `_global_interfaces` 只逐对核对相邻章节，未进行一次完整正文与总/节目标的覆盖复核。现在，在全部批准章节已实际生成、局部检查及邻接检查没有待修复问题后，调用一次 `reviewer_math`，使用 `scope.kind=chapter_coverage`。传入全部实际单元及明确的章节—目标—单元映射，保存原始回复。任何非空完整稿均执行，包括只有一节的边界情形。

全章疑点直接返回既有 `issues` 链，进入原全局修复循环：确定实际目标单元、保留审批和非目标内容、保存修复候选、重新进行受影响章节及后续检查，然后重新复核。没有新增绕过审核的写稿或直接替换产物路径。

reviewer v5 新增通用规则，不含章 ID 或具体金标公式：

- 按批准目标核对一般结论、参数域与相关边界，避免用固定参数特例冒充一般知识覆盖。目标仅要求特例时不自动扩展课程。
- 将声称适用范围内最小合法指标代入求和、部分和、移位项、递推和差分，核对所需首项、初值和约定。先查完整实际上下文；已有空和约定、已定义初值或适用域排除边界时不误报。不因出现零下标就判错。实际在合法指标处引用未定义项至少为 review，不能只给排版 warning。
- 内部单元编号需改成学生能理解的自然引用或已有真实编号，不编造标签，不删数学前提。

相邻章节审阅现提供它们之前的全部实际先修正文，避免漏看早先已定义初值而要求每节重复定义。全章审阅读取全部实际正文。此处 mock 仅验证上下文传递；不能证明真实模型一定正确理解。

确定性正文检查只识别格式明确的 `Sxx.Uyy` / `Sxx-Uyy` 工作流标识，产生定位到实际单元的 blocking 问题。注释、明确不活动分支、非打印的 label/ref 目标以及超链接目标被屏蔽；真正显示的超链接文字仍检查。数学变量 `S_0`、`S_{03}`、`U_{05}` 不匹配。没有执行盲目字符串替换。此检查不是完整 TeX 展开器；代码/verbatim 示例由既有保守屏蔽器处理，最终版面仍需视觉复核。

## 已 CHECKED 稿如何接受合法修复

候选继承已验证的缓存契约修复：reviewer 提示词 SHA 和 pipeline SHA 都被 `check_contract` 采集，更新后旧 PASS 只能作为未检查种子。先保留并验证原 checkpoint、源文件及旧前缀证据，再优先读取最新已接受的 LocalRecovery 候选，保留审批、计数和未决问题。全局强制修复种子仍优先；下游依赖变化必须重检。

增加了一个真实恢复边界：局部审阅已经完成而编译中断时，可能还没有 `section.*` checkpoint。现在，存在同一个已批准 plan/spec、同模型/提供方且路径、SHA 和依赖证据合法的 LocalRecovery 候选时，始终优先该最新合法稿继续检查，不重新调用 writer，不重置计数。因此上游变化后重新检查又中断、第三次恢复时也不会回退到旧 writer 缓存。本补丁未改动编译实现。

独立审计还发现真实 SQLite 的 steps 主键包含 input_hash，同一节可有多版本。最终候选使用 created_at 降序、rowid 降序，并逐候选验证输出 SHA 和批准身份，明确选取最近同审批版本。最新合法身份的源文件损坏时阻断，不能回退旧 PASS；不由 input_hash 的词法顺序决定版本。

主任务应在 Worker 停稳后合并、执行回归并重新启动；通过既有受审批约束的任务恢复/重检入口继续两章。新的疑点与修复须由正常工作流产生，再输出新版本。旧 TeX、PDF、日志和人工审核状态保留，不直接覆盖或倒填旧结果。

## 验证记录

- `tests/test_teaching_quality_gate.py` 新增 19 项测试：可见 ID 与合法引用/数学符号对照、全章缺口进入受限修复、完整先修上下文、拒绝用部分稿做全章验收、无 checkpoint 的连续中断与前文变化恢复、单节覆盖。
- 缓存契约测试另补 6 项真实 SQLite 多版本排序与损坏证据回退阻断用例，共 20 项。
- 既有全局/草稿/局部/引用/答案恢复模拟 provider 增加独立 `chapter_coverage` 中性回复分支，原有计数仍专门记录这些 fixture 所针对的局部或相邻阶段。草稿恢复断言改为验证最新合法 LocalRecovery 种子、全部重检与原候选未变。
- 原生产红测 **8 FAIL / 9 PASS**，证据：`teaching-quality-red.log`、`.xml`。
- 初版 combined 相关回归 **97 PASS，35.58 秒**，证据保留在 `teaching-quality-combined.log`、`.xml`；随后审计补充用例 **8 FAIL / 1 PASS**，证据 `teaching-quality-audit-red.log`、`.xml`。
- 最终 combined 候选相关回归 **105 PASS，42.60 秒**，证据：`teaching-quality-combined-02.log`、`.xml`。测试结束确认生产 pipeline 与 reviewer SHA 未改变。

模型调用全部为 mock、SQLite 全部隔离。其中 3 项实际使用 Windows XeLaTeX，分别覆盖严格局部补丁、真实捕获的定义标签和末尾答案回链；3 项均通过。其余编译使用 mock。**这些不证明提示词数学准确率或真实 API 效果。** 新提示词对实际一般几何级数覆盖、首项/索引漏洞的检出和修复效果必须在合并后的真实章节恢复中验证。人工数学与视觉验收：NOT_RUN。合并其他子任务后的完整回归由主任务执行。

主任务另行启动的冻结 v5 真实对照与本报告本地测试分开记录；出现的正例误报不能用本地 PASS 抵消。独立 v6 指代/继承精化候选不包含在此 combined 补丁中，尚未进行 API 测试。
