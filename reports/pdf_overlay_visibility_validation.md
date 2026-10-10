# Beamer 隐藏 overlay 几何诊断与回归

日期：2026-09-20。此记录只证明指定几何规则及回归；不替代教师逐页视觉验收。

## 实际异常与证据

旧矩阵 `workspace/reference-matrix/20260920-002014/` 的 CH03 两种主题在第 122 页（F108、overlay 1）出现约 x=2028、top=-1900 的文本包围盒。pypdfium2 `get_charbox` 和 pdfplumber 各自都报告 74 个页外字符；第 123 页（同 F108、overlay 2）各自报告 0 个页外字符。题干先出现，解答后出现，渲染图与这一 overlay 行为一致。双引擎坐标、图像路径、PDF SHA-256 保存在 `pdf_geometry_dual_engine_diagnosis.json`。

这不是两个抽取引擎的坐标冲突。本机实际 PGF 源码 `D:/texlive/2024/texmf-dist/tex/generic/pgf/systemlayer/pgfsys.code.tex` 第 1696 行定义 `pgfsys@begininvisible` 为 x、y 同时平移 2000bp；第 1702 行定义相反平移。Beamer 用这一机制将尚未显示的对象移出物理页。

例如默认主题第 122 页“解”的 pdfplumber bbox 为 `[2028.372,-1899.454,2036.342,-1891.484]`，同帧第 123 页可见 bbox 为 `[28.346,100.571,36.316,108.541]`。按 PDF 坐标向右、向上各 2000bp 反变换后，两者残差约 0.026pt。FDU 对应 bbox 为 `[2028.372,-1878.973,2036.342,-1871.003]` 与 `[28.346,121.052,36.316,129.022]`。

## 严格识别条件

`pdfcheck.match_pgf_hidden_character` 只在以下条件同时成立时把文本记录为 `verified_pgf_hidden_overlay_character`：

1. 实际 `.nav` 恰好覆盖所有物理页，存在已验证的 frame ID。
2. 候选可见字符来自同一 frame 的不同物理 overlay 页。
3. 字符文本、去掉 PDF subset 前缀的字体名一致，字号差不超过 0.01pt。
4. 原 bbox 按 x 减 2000、top/bottom 加 2000 校正；校正 bbox 与候选 bbox 均在物理页面内。
5. 四个坐标最大残差不超过 0.1pt。页面越界阈值仍为原来的 0.75pt，没有放宽。

每个匹配保留原始、校正和可见 bbox，frame、源页、对应 overlay 页、字符序号、残差、匹配容差，以及两张实际 PNG 的 SHA-256。原始字符计数和隐藏字符计数分别保留。全部物理页照常渲染，不跳过中间 overlay。

缺少 nav、不同 frame、没有可见对应、字体/文字/坐标不匹配、通用超页文本以及超页图片仍按原规则 blocking。嵌套隐藏产生其他偏移、隐藏图片和未支持情况不自动豁免。该规则不能证明没有遮挡、遗漏或视觉缺陷。

## 已执行测试

先加入合法 pause 的“几何应 PASS”断言，旧实现确实失败，日志 `pdf_pgf_hidden_red.log` 保留。首次绿阶段因新增测试位置误放旧测试收尾产生一个 NameError，其日志 `pdf_pgf_hidden_fixed.log` 也保留；修正测试组织后没有放宽业务断言。

最终实际命令：

```powershell
.venv\Scripts\python.exe -m pytest tests/test_compiler_pdf.py -k 'compile_chinese_path or middle_overlay or pgf_translation or layout_probe_requires' --basetemp workspace\test_pgf_hidden_validated -q
```

结果 **4 passed, 12 deselected in 8.38s**，日志 `pdf_pgf_hidden_validated.log`。

| 类别 | 实际结果 |
|---|---|
| Windows XeLaTeX 合成 pause／中文目录 | PASS：真实编译、两张物理页全渲染、nav 全覆盖、隐藏对象有可见对应 |
| Windows XeLaTeX T47 中间 overlay 真溢出 | PASS：三张物理页全渲染，第 2 页真实超界仍被标为 blocking，PDF 检查返回 FAIL |
| 离线合成坐标反例 | PASS：不同 frame、不同字符、1pt 偏差、无 nav、通用页外坐标均不豁免 |
| 离线探针指纹失效 | PASS：引擎或模板改变后，不复用旧校准估计 |
| 真实供应商 API | NOT_RUN：本次没有 API 调用 |
| 教师人工视觉验收 | NOT_RUN：自动化与实现者定位图像不代替教师验收 |

真实源三章双模板全页结果由 `reference_matrix.json` 及其矩阵验证报告单独记录；本报告不把六组自动几何检查升级为教师审核通过。
