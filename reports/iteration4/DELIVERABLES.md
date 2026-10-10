# 最终交付清单

独立Windows本地应用已实现，当前三章讲义完成自动工作流与交付核验，均待教师审核。以下链接绑定当前实际文件SHA；旧稿、失败日志和检查点均保留。

[启动与环境说明](<D:/研究生阶段/数学教学agent/math-teaching-agent/README.md>) · [分层验收报告](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/FINAL_ACCEPTANCE.md>)

应用入口：[新建任务](http://127.0.0.1:8765)；[三章基准任务](http://127.0.0.1:8766)。如服务未运行，按README启动相应工作区。

## 真实API生成讲义

|章|页数／累计请求|PDF|TeX|完整源码ZIP|检查与对照|
|---|---|---|---|---|---|
|CH01|11 / 70|[PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/vb45236bedc6b/build/lecture.pdf>)|[TeX](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/vb45236bedc6b/source/lecture.tex>)|[ZIP](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/vb45236bedc6b/source_bundle.zip>)|[原稿对照/审读](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/ch01-final-audit-20260924-final/final-audit.md>) · [自动检查](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/vb45236bedc6b/quality_report.json>)|
|CH02|18 / 152|[PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/fd6736af6ef14be3/ve87618f98837/build/lecture.pdf>)|[TeX](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/fd6736af6ef14be3/ve87618f98837/source/lecture.tex>)|[ZIP](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/fd6736af6ef14be3/ve87618f98837/source_bundle.zip>)|[原稿对照/审读](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/ch02-final-audit-20260924T0316/final-audit.md>) · [自动检查](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/fd6736af6ef14be3/ve87618f98837/quality_report.json>)|
|CH03|23 / 191|[PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/v760263ba5b8b/build/lecture.pdf>)|[TeX](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/v760263ba5b8b/source/lecture.tex>)|[ZIP](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/v760263ba5b8b/source_bundle.zip>)|[原稿对照/审读](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/ch03-final-audit-20260923T1451/final-audit.md>) · [自动检查](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/v760263ba5b8b/quality_report.json>)|

## 原资料转双模板课件

这六组为真实本机解析、排版和编译产物，不计为模型生成测试。共522个物理页的历史渲染保留；全部六个ZIP已有干净目录编译证据（此前2组、本轮补4组）。教师逐页验收未执行。

|数据/模板|页数|PDF|TeX|源码ZIP|
|---|---|---|---|---|
|CH01-default|77|[PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-013122-adaptive-v2-default/CH01-default/build/slides.pdf>)|[TeX](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-013122-adaptive-v2-default/CH01-default/source/slides.tex>)|[ZIP](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH01-default/source_bundle-v2.zip>)|
|CH01-fduclassroom|77|[PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-012826-adaptive-v2/CH01-fduclassroom/build/slides.pdf>)|[TeX](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-012826-adaptive-v2/CH01-fduclassroom/source/slides.tex>)|[ZIP](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH01-fduclassroom/source_bundle-v2.zip>)|
|CH02-default|76|[PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-013122-adaptive-v2-default/CH02-default/build/slides.pdf>)|[TeX](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-013122-adaptive-v2-default/CH02-default/source/slides.tex>)|[ZIP](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH02-default/source_bundle-v2.zip>)|
|CH02-fduclassroom|76|[PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-012826-adaptive-v2/CH02-fduclassroom/build/slides.pdf>)|[TeX](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-012826-adaptive-v2/CH02-fduclassroom/source/slides.tex>)|[ZIP](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH02-fduclassroom/source_bundle-v2.zip>)|
|CH03-default|108|[PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-013122-adaptive-v2-default/CH03-default/build/slides.pdf>)|[TeX](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-013122-adaptive-v2-default/CH03-default/source/slides.tex>)|[ZIP](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH03-default/source_bundle-v2.zip>)|
|CH03-fduclassroom|108|[PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-012826-adaptive-v2/CH03-fduclassroom/build/slides.pdf>)|[TeX](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-012826-adaptive-v2/CH03-fduclassroom/source/slides.tex>)|[ZIP](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH03-fduclassroom/source_bundle-v2.zip>)|

原生XeLaTeX采用trusted_local模式，不是文件系统/网络隔离沙箱。所有讲义的数学/策略检查仍保留NEEDS_REVIEW，agent审读不代替教师签认。

[文件SHA、请求与验收绑定](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/delivery-manifest.json>)
