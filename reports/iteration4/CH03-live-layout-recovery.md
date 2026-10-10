# CH03 S05.U22 真实布局恢复记录

捕获时间：2026-09-20T16:02:10.424280+00:00。任务 `a45be503af594ce8aae0bb1e4c30184b`；当前状态 **REPAIRING / repair.global.S04**，累计请求 58。任务仍在全章审阅/修复链中，**不是最终交付**。

本报告只读既有证据，没有发 API、重新编译或渲染 PDF。下列编译均是已经执行的真实 Windows XeLaTeX，不是 mock。Agent 全页目视、教师数学和教师视觉均为 **NOT_RUN**。

## 三次真实编译证据

| 阶段 | 编译目录 | 结果 | 两遍耗时 / 页数 | 源码 SHA-256 | PDF SHA-256 |
|---|---|---|---|---|---|
| historical_fail | [sS05_79367048d571](../../workspace/iteration2-live/b/a45be503af594ce8/sS05_79367048d571/compile.json) | FAIL | 3.344 s / 17 | `17e3a09495be8fbe8e39abdff18a7ecd88ba52d68f55f926153bdac9246e3800` | `fc4f197ddc0ca8038f73a76e115b20ebe598d96179fbfaf6d3e303a90a7c2d5c` |
| resumed_fail | [sS05_bd250159fdc5](../../workspace/iteration2-live/b/a45be503af594ce8/sS05_bd250159fdc5/compile.json) | FAIL | 3.86 s / 17 | `f0e6cbd3d0ae950704e7ecd800d30103b89a32c0d7ea1f33b6a34ad6b7dfdd92` | `4800ca1767c8640580df6c6d4010156cbaec4c4fbc693cd391ec071533d10b70` |
| after_accepted_layout_patch | [compile-attempt-1](../../workspace/iteration2-live/b/a45be503af594ce8/sS05_bd250159fdc5/compile-attempt-1/compile.json) | PASS | 3.75 s / 17 | `08ebb7ecb31a5d7788058d7e46b210ec34c0f365085538c1d87ab411cb96403c` | `8f406bedbb39d5d179935021947d6888e066c0ae079637d8e383a605f6201462` |

前两次的 `OVERFULL_BOX` 都是 `Overfull \hbox (0.5104pt too wide) in paragraph at lines 932--933`。源码第 912 行标识 `% UNIT S05.U22`，932 行结束表格公式，933 行是一段连续文字与内联数列。当前映射将完整报错区间唯一定位到 S05.U22，未把上游章节改为修复目标。

## 接受的修复及保留的数学

[原始局部补丁](../../workspace/iteration2-live/b/a45be503af594ce8/sS05_bd250159fdc5/repair-1-patch.json) 的 raw SHA 为 `f24c25fc703d378d562f6d9858af7b40bd7b9a660573a79eee2ba2aee6c4fe69`。补丁仅替换 S05.U22，将“所得函数连续且非负……”后分段，五个超额需求值改为独立陈列公式；后面仍指出三个开区间各有一个零点。修后源码对应行 933–939。未删除数学内容、缩小字号、提高容差或隐藏警告。

独立对比候选 JSON：单元总数、顺序、ID、kind、关联题号及非目标单元逐项不变；仅 S05.U22.tex 改变，全部计算请求/限制/疑点元数据不变。当前 LocalRecovery 记录 proposal_calls=1、applied_rounds=1、S05.U22 实际修改=1、rejected_proposals=0，没有清零旧失败。

题解仍以 E(1)=9>0、E(5)=-4<0 证明存在；额外需求严格递减、供给严格递增使 E 严格递减，才推出唯一。原条件下所给分段线性非负函数仍产生 9,-1,3,-1,-4，前三段连续且端点异号，确实允许多个均衡点。

## 数学审阅与编译分开判定

- historical_fail：[模型原审阅](../../workspace/iteration2-live/b/a45be503af594ce8/sS05_79367048d571/local-0-review-0.json)，raw SHA `0333aff2d04c317efa10c7cf31987cee17e451f7028f60ba7aa6beb41408ff7a`，22 个实际单元，issues=0；输出规范化哈希匹配模型：gpt-6-astra。
- resumed_fail：[模型原审阅](../../workspace/iteration2-live/b/a45be503af594ce8/sS05_bd250159fdc5/local-0-review-0.json)，raw SHA `38a21180adecee8a39fc79724928f5fe23035e5f17a9c0430b5ebaa8ca276209`，22 个实际单元，issues=0；输出规范化哈希匹配模型：gpt-6-astra。
- after_accepted_layout_patch：[模型原审阅](../../workspace/iteration2-live/b/a45be503af594ce8/sS05_bd250159fdc5/local-1-review-0.json)，raw SHA `829929662718518717e804ff8b8275a3021fce2176b0c551876f7f17cf1e8e44`，22 个实际单元，issues=0；输出规范化哈希匹配模型：gpt-6-astra。

修后模型说明旧日志不能证明新源码仍溢出，并明确没有编译或检查最终 PDF；它没有冒称排版成功。随后 `compile-attempt-1` 实际运行两遍 XeLaTeX，返回 PASS、issues=[]、17 页。这一编译结果仅解决该版源码的机器可检测问题，不能替代逐页视觉或教师验收。

补丁证据中的 `APPLIED_UNCHECKED`、math_check=NOT_RUN 是接受补丁时保存的历史阶段，不应覆盖成后验 PASS。后续 CHECKED 状态、局部数学审阅和独立新目录编译结果另行保存。

[完整 JSON、每个编译报告/四份日志 SHA、模型请求匹配、原补丁与检查点](CH03-live-layout-recovery.json)

最终冻结后仍需逐条核查 22 项 REQUIRED 与 G01–G08，映射 unit/TeX 行/PDF 物理页，逐页目视并验证源 ZIP 重编译。当前 17 页累计节编译稿不能提前当作最终 PDF。
