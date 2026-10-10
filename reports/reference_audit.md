# M0 三章参考资料审计

检查时间：2026-09-19T15:37:25.031279+00:00

范围：仅用户指定的第一章、第二章、第三章。全部原件只读；未扫描其他个人目录。

| 数据集 | 文件数 | 讲义 TeX/PDF | Beamer TeX/PDF | 本地资源闭包 | 新编译 | 人工视觉 |
|---|---:|---|---|---|---|---|
| CH01 第一章 | 17 | PRESENT | PRESENT | PASS | NOT_RUN | NOT_RUN |
| CH02 第二章 | 17 | PRESENT | PRESENT | PASS | NOT_RUN | NOT_RUN |
| CH03 第三章 | 17 | PRESENT | PRESENT | PASS | NOT_RUN | NOT_RUN |

## 实际发现

- 清单包含 51 个真实文件，每个均记录大小、SHA-256、角色、编码、发现状态和引用行号；三份同名讲义以 dataset_id/relative_path/sha256 区分。
- FDU 主题共 3 份，实际不同 SHA-256 数量 1；选定指纹 `98d46f69b226ebf615e428d2895473aacc90ab9483df62ee78358e6d5bfedf43`，三份字节相同，无需任意挑选不同版本。
- 每组主题第 87 行引用 resources/fudan，均精确解析为同目录 resources/fudan.pdf；未发现缺失本地静态引用资源。
- 三组的讲义与课件入口均为 UTF-8。主题为 ASCII 兼容的 UTF-8。二进制 PDF/压缩辅助文件编码记录为 null。
- 显式的 TeX 宏包/文档类使用已解析绝对路径 D:/texlive/2024/bin/windows/kpsewhich.exe 检查；查找不等同于编译成功。
- 参考讲义包含 NewDocumentEnvironment 自定义数学环境，proofdetail/solution 题解及 extra 选读内容，解析器应保留原文区间。
- Beamer 的三态章节目录位于各主 TeX 的 AtBeginSection；仅复制 sty 不足以复制目录行为。
- 旧主题有 title=LARGE、frametitle=Large、itemize scriptsize/tiny；主源有 tiny 宏定义及顶部 0.5cm 额外空白。须独立适配当前四档字号，不能直接视为合格输出；静态出现不证明所有分支实际使用。
- 第三章讲义包含二元函数、Landau 符号和选读内容；章节标签用于检索，不自动注入新的课程计划。
- 讲义习题标题标作第 2/3/4 章，目录样例命名为第 1/2/3 章；仅记录此差异，不改原件。

## 未执行与限制

- 新编译、PDF 页数/渲染/字体几何、逐单元讲义课件对齐、教师人工视觉审核：NOT_RUN。baseline_metrics 对未测值使用 null。
- 原目录里的 PDF/log/aux 是历史产物；不作为当前工程或新 Windows 编译通过证据。
- 本轮仅只读审计，未创建运行输入快照；实际导入必须按哈希制作不可变副本。
- 依赖闭包覆盖所有现有 TeX/sty 的字面文件引用、主题和宏包，未执行任意宏展开；字体和动态条件依赖留待编译验证。
- 原主题与图像分发许可未核实，仅本机使用，不擅自公开分发。

机器证据：reference_index/manifest.json、style_profile.json、lecture_beamer_alignment.json、baseline_metrics.json。

M3—M5 动态补充：真实编译查出 CH01 第314行 BradyWeil、CH02 第722行 NCBISteadyState、CH03 第650行 NCBIEnzyme 和第1388行 BradyWeil 为未定义文献引用。三份源第100行的 upcite 实際展开 cite，原稿没有相应 bibitem/bibliography；完整证据和补齐方法见 reports/reference_dynamic_findings.md。原PDF后续已全页渲染233页，实测值见 baseline_metrics.json；教师审核仍 NOT_RUN。
