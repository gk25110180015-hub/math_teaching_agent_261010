# 第二轮：三章 Beamer 真实基准对照与实现改进

本轮比较使用用户三份原讲义、三份原 Beamer，以及上轮六份完整草稿。新增全稿只用于在独立工作副本补齐其真实书目条目，原数学正文不改写，原件不覆盖。本比较脚本没有调用模型 API；真实 API 验证由工程另一份报告单独记录。

## 结果

六组均完成真实 Windows XeLaTeX 编译与来源核对，默认/FDU各为77、76、108页，共522物理页全部渲染。几何检查无 blocking，仍保留 NEEDS_REVIEW；教师逐页人工验收 NOT_RUN。原51文件哈希复核PASS。

| 章 | 原参考页 / 逻辑帧 | 上轮页 / 逻辑帧 | 本轮页 / 逻辑帧 | 本轮正文 normal / small / foot | 原 / 上轮 / 本轮内部字符中位数 |
|---|---:|---:|---:|---:|---:|
| CH01 | 54 / 40 | 88 / 85 | 77 / 74 | 54 / 7 / 7 | 163.5 / 55 / 71.0 |
| CH02 | 51 / 39 | 78 / 71 | 76 / 69 | 45 / 14 / 3 | 133 / 98 / 94 |
| CH03 | 93 / 71 | 127 / 112 | 108 / 93 | 61 / 12 / 13 | 128 / 85.0 / 106 |

上表两模板页数相同。字符密度使用所有逻辑帧的最后overlay，在相同内部窗口统计可见字形；排除了隐藏overlay、导航和页脚的大部分影响，但它只是描述性指标，不能据此判定教学质量。第二章的字符中位数98→94同时字号和内容行数增加，不能为了提高数值而挤小正文。

## 查明并修复的不足

1. 上轮全部正文固定footnotesize，短页仍显示过小。本轮逐frame尝试正常字号，只有较长完整单元使用small/footnotesize。显式font_size仍保留为可追踪回退；应用应优先使用`_layout={'split_long':True}`。
2. 长证明/custom按每段或item逐页输出，没有再次组合完整步骤。本轮在源区间连续、环境平衡、容量允许时组合，不截断公式。CH03 U0038从11帧变3帧；U0051完整item从6帧变2帧。来源检查独立对实际TeX逐区间核对，重复环境上下文单独标记。
3. 邻接短解释段落原来各占一页，现只在相同section、同类解释且容量允许时组合；不把互不相关的数学命题强行拼页。
4. 目录原来超过10条就增加目录页。本轮依次尝试合法字号/间距、稳定双列、显式分页，每个section仍有一次完整三态目录组。12/24节真实FDU探针分别24/48物理页，编译与几何均PASS，所有标题保留。
5. 单纯文本/公式计数漏估嵌套theorem、custom、proofdetail等环境的垂直开销。第一轮自适应CH03出现两个真实vbox溢出，已保留失败日志/107页PDF；修复估算后第二轮完整108页无OVERFULL。
6. thebibliography现以独立源单元渲染，按完整bibitem明确分页，不用allowframebreaks，每个条目只输出一次。补充自新全稿的BradyWeil、NCBISteadyState、NCBIEnzyme有原文、行号和hash provenance；未猜测书目。

## 与原参考仍有的内容和呈现差异

原参考54/51/93页不是应当强行追平的目标。第一章原参考5个section，当前讲义6个；第二章原参考5个，讲义7个；第三章均7个但知识点分组标题不同。原课件是重新组织过的教学文本，本轮保持批准来源的正文与证明，不能用减页代替内容审核。具体两组section名称存于JSON。

当前目录数为6/7/7，原参考为5/5/7；这是section结构差异，三章旧目录本身没有重复hook。12/24节容量问题由独立夹具揭示，而非误称旧三章因目录重复而膨胀。原参考overlay额外物理页为14/12/22，本轮为3/7/15；本轮在明确短题解组合处展示题干→解答，不机械复制参考课件每个动画步骤。

原第一/第二章参考源码存在scriptsize，本轮不继承这些违规字号。FDU原sty字节复制，适配层保持当前section导航和完整章节目录；这避免在允许最小字号下把长的全章导航挤出页宽，并非像素级复刻旧PDF。

## 实际测试与保留条件

离线结构/保真回归：新增4个问题先4项FAIL，修改后连同书目与原解析回归36项PASS。目录容量为真实Windows编译与72页全渲染。三章双模板522页为真实Windows编译、所有overlay渲染、来源FID PASS；几何review提示与教师验收未混记。

保留的review主要为正文靠近实测正文边界；CH03自然公式下标中文和FandolHei斜体替换另需复核。实现者抽看了CH01原参考/新稿、CH03完整3页证明PNG，确认本次组合无明显裁切；这不等于教师对522页逐页通过。

| 数据集 / 模板 | 编译 | FID | 完整性 | 实际/已渲染页 | 几何 | blocking |
|---|---|---|---|---:|---|---:|
| CH01 / default | PASS | PASS | COMPLETE_DRAFT | 77 / 77 | NEEDS_REVIEW | 0 |
| CH01 / fduclassroom | PASS | PASS | COMPLETE_DRAFT | 77 / 77 | NEEDS_REVIEW | 0 |
| CH02 / default | PASS | PASS | COMPLETE_DRAFT | 76 / 76 | NEEDS_REVIEW | 0 |
| CH02 / fduclassroom | PASS | PASS | COMPLETE_DRAFT | 76 / 76 | NEEDS_REVIEW | 0 |
| CH03 / default | PASS | PASS | COMPLETE_DRAFT | 108 / 108 | NEEDS_REVIEW | 0 |
| CH03 / fduclassroom | PASS | PASS | COMPLETE_DRAFT | 108 / 108 | NEEDS_REVIEW | 0 |

详细产物位置：
- `D:\研究生阶段\数学教学agent\math-teaching-agent\workspace\iteration2-beamer\20260920-012826-adaptive-v2\comparison.json`
- `D:\研究生阶段\数学教学agent\math-teaching-agent\workspace\iteration2-beamer\20260920-013122-adaptive-v2-default\comparison.json`

- before快照：`reports/iteration2/beamer_comparison_before.json`及`before-source/`。
- 失败/特征回归：`reports/iteration2/layout_regressions_before.txt`。
- 原稿与补书目来源：`reports/iteration2/source_audit.json`及每组prepared-inputs/*.provenance.json。
- 教师评价、难度一致性、数学原稿本身的正确性仍需要独立审核；本轮没有训练模型权重，也没有宣称盲测准确率。
