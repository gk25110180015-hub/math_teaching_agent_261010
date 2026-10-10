# 动态编译发现的原资料问题

这些是 M3—M5 真实 XeLaTeX 构建对 M0 静态文件闭包的补充；不意味着 M0 的文件存在性检查包含了数学或文献正确性核对。

| 数据集 | 原始源文件 | 精确行号 | 未定义文献键 |
|---|---|---:|---|
| CH01 | 第一章/大学数学（一）(1).tex | 314 | BradyWeil |
| CH02 | 第二章/大学数学（一）(1).tex | 722 | NCBISteadyState |
| CH03 | 第三章/大学数学（一）(1).tex | 650 | NCBIEnzyme |
| CH03 | 第三章/大学数学（一）(1).tex | 1388 | BradyWeil |

三份源文件第 100 行定义 `\upcite`，其展开明确调用 `\cite{#1}`，不是无依赖的纯文本标记。实际三章讲义内没有 `\bibitem`、`\bibliography` 或 `thebibliography`；实际 XeLaTeX 日志产生 undefined citation。系统保留原引用并阻止合格发布，不编造条目或删除引用。

当前上传在确认后为不可变快照。补齐原稿书目后应上传新的完整 TeX/ZIP、检查内容清单并重新确认；不能在后台偷偷修改旧审批输入。原输入不变的编译失败可保留原审批重试。

原始 `\iffalse ... \fi` 区域不产生排版内容。解析器现在保存整个区间为带原始偏移与哈希的 inactive 单元；渲染报告单列 inactive_source_units，不把被原稿禁用的数学内容打开，也不跨 frame 破坏条件配对。

原 PDF 已实际渲染全部 233 个物理页：讲义 9/10/16 页；Beamer 54/51/93 页，对应实际 .nav 的 40/39/71 个逻辑 frame。教师逐页审核仍为 NOT_RUN。页级测量见 reference_index/baseline_metrics.json；原样例课件有几何风险，不可将旧样例视为当前硬规则已合格。
