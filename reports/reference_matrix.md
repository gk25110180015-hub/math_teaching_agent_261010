# 三章实际源 → 双模板六组验收矩阵

六组均实际读取用户原讲义并尝试默认/FDU主题。方法是确定性源保真转换，真实 API 未调用；教师视觉审核 NOT_RUN。前轮按 normalsize → small → footnotesize → 完整语义边界拆分逐候选实测；代码修复后在新目录复测最终候选，前轮所有源码、PDF和日志保留。

| 数据集 | 模板 | 编译验收 | PDF完整性 | 最后候选物理页 | 已渲染页 | 来源原文检查 | 页面几何 | 教师审核 |
|---|---|---|---|---:|---:|---|---|---|
| CH01 | default | FAIL | COMPLETE_DRAFT | 88 | 88 | PASS | NEEDS_REVIEW | NOT_RUN |
| CH01 | fduclassroom | FAIL | COMPLETE_DRAFT | 88 | 88 | PASS | NEEDS_REVIEW | NOT_RUN |
| CH02 | default | FAIL | COMPLETE_DRAFT | 78 | 78 | PASS | NEEDS_REVIEW | NOT_RUN |
| CH02 | fduclassroom | FAIL | COMPLETE_DRAFT | 78 | 78 | PASS | NEEDS_REVIEW | NOT_RUN |
| CH03 | default | FAIL | COMPLETE_DRAFT | 127 | 127 | PASS | NEEDS_REVIEW | NOT_RUN |
| CH03 | fduclassroom | FAIL | COMPLETE_DRAFT | 127 | 127 | PASS | NEEDS_REVIEW | NOT_RUN |

## 具体阻塞与修复证据

- 三份原讲义存在未定义文献引用：CH01 第314行 BradyWeil；CH02 第722行 NCBISteadyState；CH03 第650行 NCBIEnzyme、第1388行 BradyWeil。未发现配套 bibitem/bibliography，不编造参考条目，也不删除引用。
- 实测发现的 CRLF 重复、条件分支跨帧、boxed 数学环境切分、solution 环境重定义等实现错误已分别复现并修复，保留旧失败产物。当前 parser/Beamer 离线回归31项PASS，另T07/T09两项PASS，T31独立Windows阻塞回归PASS；这不是API或教师验收。
- CH03 U0028 大TikZ图采用局部等比例坐标调整，未启用transform shape，节点文字不缩放；U0051长custom列表在完整item边界分页并重复必要上下文；U0076编号改用局部默认数字标签。原文payload全部独立核对。
- 上一轮巨大越界对象对应首overlay被Beamer移到画布外的隐藏解答。实现者实际核对过CH01页9与CH03页122/123图像；这仅是抽样诊断，不替代教师逐页验收。未知越界不豁免；本轮检查器实测规则与精确物理页、frame、单元、bbox见JSON。
- 每组最后一个候选的全部物理页（包含 overlay）已尝试渲染，未因产生PDF而冒称编译验收通过。前面的失败候选保留源码/PDF/日志，不宣称逐页验收。
- 51 个原始参考文件重新 SHA-256 核对：PASS；未改变原件。

全部候选与检查证据：`D:\研究生阶段\数学教学agent\math-teaching-agent\workspace\reference-matrix\20260920-003905`。

原始参考 PDF 的实测基线见 reference_index/baseline_metrics.json：三组讲义 9/10/16 页、课件 54/51/93 页；共233物理页已经实际渲染。它们不是当前新转换通过证据。

### CH01 / default

- UNRESOLVED_REFERENCE: LaTeX Warning: Citation `BradyWeil' on page 27 undefined on input line 19.
- UNRESOLVED_REFERENCE: LaTeX Warning: There were undefined references.
- 页面几何blocking统计：`{}`。
- 页面几何所有规则统计（含review）：`{"BODY_REGION_CONTACT": 46}`。

### CH01 / fduclassroom

- UNRESOLVED_REFERENCE: LaTeX Warning: Citation `BradyWeil' on page 27 undefined on input line 19.
- UNRESOLVED_REFERENCE: LaTeX Warning: There were undefined references.
- 页面几何blocking统计：`{}`。
- 页面几何所有规则统计（含review）：`{"BODY_REGION_CONTACT": 46}`。

### CH02 / default

- UNRESOLVED_REFERENCE: LaTeX Warning: Citation `NCBISteadyState' on page 77 undefined on input line 24.
- UNRESOLVED_REFERENCE: LaTeX Warning: There were undefined references.
- 页面几何blocking统计：`{}`。
- 页面几何所有规则统计（含review）：`{"BODY_REGION_CONTACT": 34}`。

### CH02 / fduclassroom

- UNRESOLVED_REFERENCE: LaTeX Warning: Citation `NCBISteadyState' on page 77 undefined on input line 24.
- UNRESOLVED_REFERENCE: LaTeX Warning: There were undefined references.
- 页面几何blocking统计：`{}`。
- 页面几何所有规则统计（含review）：`{"BODY_REGION_CONTACT": 34}`。

### CH03 / default

- UNRESOLVED_REFERENCE: LaTeX Warning: Citation `NCBIEnzyme' on page 43 undefined on input line 20.
- UNRESOLVED_REFERENCE: LaTeX Warning: Citation `BradyWeil' on page 114 undefined on input line 10.
- UNRESOLVED_REFERENCE: LaTeX Warning: There were undefined references.
- 页面几何blocking统计：`{}`。
- 页面几何所有规则统计（含review）：`{"BODY_REGION_CONTACT": 49, "SUSPICIOUS_SMALL_CJK": 1}`。

### CH03 / fduclassroom

- UNRESOLVED_REFERENCE: LaTeX Warning: Citation `NCBIEnzyme' on page 43 undefined on input line 20.
- UNRESOLVED_REFERENCE: LaTeX Warning: Citation `BradyWeil' on page 114 undefined on input line 10.
- UNRESOLVED_REFERENCE: LaTeX Warning: There were undefined references.
- 页面几何blocking统计：`{}`。
- 页面几何所有规则统计（含review）：`{"BODY_REGION_CONTACT": 50, "SUSPICIOUS_SMALL_CJK": 1}`。
