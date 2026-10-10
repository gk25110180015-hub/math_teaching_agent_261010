# 解析与 Beamer 模块的实际阶段证据

Windows 11 本机，新工程 `math-teaching-agent`，原始三章资料均保留。本文记录实现测试，真实 API 与教师视觉审核不混记。

## M0

完整只读审计三章51文件。TeX/sty字面依赖及显式宏包均找到；3份FDU主题SHA-256相同：`98d46f69b226ebf615e428d2895473aacc90ab9483df62ee78358e6d5bfedf43`。后续实际编译发现原文四处缺文献条目，已补记精确行到 reference_dynamic_findings.md，原M0静态依赖完备不代表语义引用完备。

原始六份PDF实际全部渲染233物理页；讲义9/10/16页、课件54/51/93页。原始课件存在几何风险，不作为模板验收通过证据。教师审阅、基于教师评价的采纳率仍NOT_RUN/null。

## M1/M3/M4离线逻辑回归

最新实际命令：`.venv\Scripts\python.exe -m pytest tests/test_parsing_beamer.py tests/test_source_acceptance.py -m 'not windows_compile' -q -p no:cacheprovider`，结果 **33 passed, 1 deselected in 0.37s**（parser/Beamer31项，T07/T09两项；另T31已独立真实Windows执行通过）。这些是离线unit/mock级逻辑测试，没有真实模型调用。

覆盖：精确删除及题解关联；原文区间和source hash；标准数学宏；保真检查独立比较实际输出及数学篡改；四档字号；ZIP越界、危险附件与TeX拒绝；不透明/条件禁用内容保留；verbatim；长证明/列表语义分页；明确新增数学TeX及section核对；三章主题真实hash、缺资源不可回退；Windows CRLF；boxed内array完整性；主题编号标签；大TikZ局部坐标调整及不重复图形。

先红后绿证据：实现前缺parser模块；首轮T52漏拦openin0为12pass/1fail，修复后13pass；最后长custom列表与TikZ专项为27pass/2fail，修复后29pass，再补图形不重复回归30pass。中间所有真实编译候选目录未删除。

## Windows真实编译与全页渲染

XeLaTeX实际路径 `D:\texlive\2024\bin\windows\xelatex.exe`。双模板简短探针最后各7物理页编译/渲染通过，证据 `workspace/beamer-probe/20260920-001035`。真实三章×两模板候选矩阵见 `reports/reference_matrix.json/md`，来源FID六组PASS。最终一轮 `workspace/reference-matrix/20260920-003905` 已消除全部OVERFULL与纯分页命令空frame，共586物理页全部真实渲染，六份都是COMPLETE_DRAFT、几何NEEDS_REVIEW且0 blocking。编译验收因原书目缺失仍FAIL/BLOCKED，CH03另有FandolHei斜体替换review。

矩阵中的页数、完整性、全页图像、frame/overlay映射和几何风险以逐PDF实测JSON为准。实现者抽看过少数PNG以诊断隐藏overlay与图形布局，不宣称教师逐页人工视觉验收。

真实API：NOT_RUN。教师人工视觉验收：NOT_RUN。trusted_local模式的静态预检不是操作系统沙箱。
