# 三章双模板实际几何诊断

最新候选 `workspace/reference-matrix/20260920-003905`，全部物理页渲染和精确问题以 `reports/reference_matrix.json` 及各候选 `pdf.json` 为准。原资料不变，所有旧失败目录保留。教师逐页人工审核 NOT_RUN。

## 实际布局缺陷与安全修复

- CH03 U0028：单位圆TikZ原 `scale=3` 图形自身过高；原FDU编译出现26.17352pt vbox。语义分成引入、完整图形与后续推导，图形所在局部分组只给坐标0.75等比例调整，未启用transform shape，节点字体不缩放。源payload仍逐字核对。实现者已看修复后的图形PNG，图、坐标轴及字母均在页面内。
- CH03 U0051：custom内部六个完整等价关系item原整体14.06349pt超高，现按完整item分页，外层环境和必要共同前提以标记的上下文重复，不拆公式。
- CH03 U0076：原FDU enumerate mini圆形模板放不下 `(1)` 标签，四次hbox各2.506pt。仅该编号上下文使用默认标签模板，保持序号含义；原sty不改。
- article纯 `Needspace`/`clearpage` 导致空内容frame，现识别为排版scaffold，保留原文/span/hash账目，数学单元来源核对不变。

上述最新六组编译均已无OVERFULL。编译仍因原稿缺书目条目阻塞，不能以有完整PDF冒称通过。

## 首overlay的隐藏文本

旧轮CH03 default物理页122/frameF108的隐藏“解”被提取到约x2028、y-1900；下一页123同帧解答正常出现。CH01页9/10等也具有同样情况。实现者实际查看过对应PNG，题干首层及解答次层画面正常。PDFium和pdfplumber都提取隐藏字符，原因是本机pgfsys.code.tex:1696的begininvisible将内容平移[+2000,+2000]pt，并非提取器相互矛盾。

检查器现只在 `.nav` 验证同一逻辑帧且另一overlay存在可见同字符、同字体、同字号，减去精确PGF平移后四边bbox差≤0.1pt时，将该对象登记为隐藏overlay；保留原/校正/可见bbox、双页面与字符序号、PNG SHA-256。未知越界仍阻塞；真实中间overlay越界回归仍FAIL。实现测试与证据见 `reports/pdf_pgf_hidden_validated.log`。这没有放宽通用页面边界阈值。

## 保留的人工审阅项

BODY_REGION_CONTACT是正文首行接近实测探针的安全边界提示（例如default正文top27.629pt、FDU48.254pt），并非自动断定实际遮挡。保留精确字bbox与页图供教师核对。

CH03两模板物理页88/frameF081/U0063的SUSPICIOUS_SMALL_CJK对应原数学公式 `\underbrace{x}_{\text{一阶}}` 与 `\underbrace{\sqrt{x}}_{\text{低阶}}` 的下标，实测5.978pt，正文仍为footnotesize；实现者已实际查看该页PNG，未将数学下标改写。检查器保守保留review，不宣称人工验收通过。

CH03编译另提示FandolHei中文斜体不可用而替换字体，保持review。所有精确页码/frame/单元/bbox见最终矩阵JSON；此文的旧失败编号带明确轮次，不能当作当前源文件行号。
