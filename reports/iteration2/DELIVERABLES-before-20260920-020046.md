# 第二轮课件交付清单

六组均由真实三章讲义转换，使用完整原稿中可追溯的书目补充；原资料与既有 case 文件未覆盖。全部六组原构建的 Windows XeLaTeX 与来源核验已 PASS，共 522 个物理页已渲染，自动几何仍 NEEDS_REVIEW。以下都是待教师复核的草稿。

ZIP 来自各组实际 `case/source`，包含主 TeX、实际主题/字体/风格适配与所需图片，并附 README、MAIN_FILE、compile_manifest 和逐文件 SHA-256。请优先下载 ZIP；单独主 TeX 可能缺少相邻依赖。所有链接为本机绝对路径。

| 章节 / 模板 | PDF | 主 TeX | 完整源码 ZIP | 页数 | 新目录重编译 |
|---|---|---|---|---:|---|
| CH01-default | [PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-013122-adaptive-v2-default/CH01-default/build/slides.pdf>) | [slides.tex](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-013122-adaptive-v2-default/CH01-default/source/slides.tex>) | [source_bundle.zip](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH01-default/source_bundle.zip>) | 77 | NOT_RUN |
| CH01-fduclassroom | [PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-012826-adaptive-v2/CH01-fduclassroom/build/slides.pdf>) | [slides.tex](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-012826-adaptive-v2/CH01-fduclassroom/source/slides.tex>) | [source_bundle.zip](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH01-fduclassroom/source_bundle.zip>) | 77 | NOT_RUN |
| CH02-default | [PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-013122-adaptive-v2-default/CH02-default/build/slides.pdf>) | [slides.tex](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-013122-adaptive-v2-default/CH02-default/source/slides.tex>) | [source_bundle.zip](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH02-default/source_bundle.zip>) | 76 | NOT_RUN |
| CH02-fduclassroom | [PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-012826-adaptive-v2/CH02-fduclassroom/build/slides.pdf>) | [slides.tex](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-012826-adaptive-v2/CH02-fduclassroom/source/slides.tex>) | [source_bundle.zip](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH02-fduclassroom/source_bundle.zip>) | 76 | NOT_RUN |
| CH03-default | [PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-013122-adaptive-v2-default/CH03-default/build/slides.pdf>) | [slides.tex](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-013122-adaptive-v2-default/CH03-default/source/slides.tex>) | [source_bundle.zip](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH03-default/source_bundle.zip>) | 108 | NOT_RUN |
| CH03-fduclassroom | [PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-012826-adaptive-v2/CH03-fduclassroom/build/slides.pdf>) | [slides.tex](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-012826-adaptive-v2/CH03-fduclassroom/source/slides.tex>) | [source_bundle.zip](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH03-fduclassroom/source_bundle.zip>) | 108 | NOT_RUN |

所有六份 ZIP 的成员、CRC 与 SHA-256 均已核对；原 source 与已编译 PDF 哈希保持一致。CH01/default 与 CH03/FDU 在全新解压目录使用真实 XeLaTeX 重新编译，检查实际页数和全部页面提取文字是否与基线一致。其它四份未再次重编译，其原 case 编译 PASS 与 ZIP 逐文件哈希一致为本次证据边界。复编译未再次渲染全部页面，原六组全页 PNG 已保留。

[交付及重编译机器记录](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/delivery-20260920-015918.json>)。其中包含每个 ZIP 的哈希、全部成员哈希和独立编译结果/日志路径；失败也原样保留。

相关证据：[三章双模板比较](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/beamer_comparison.md>)；[完整原稿来源审计](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/source_audit.md>)；[界面与书目回归](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/ui_validation.md>)；[第二轮验收草稿](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/acceptance_template.md>)。

教师数学/逐页视觉验收：NOT_RUN。本次打包/复编译的真实 API 调用：0。原生 trusted_local 不是隔离沙箱。FDU 私人主题与图片的公开再分发许可未认定。真实模型生成的讲义产物仍由主任务确认后另行补入，当前清单不将它们记为通过。
