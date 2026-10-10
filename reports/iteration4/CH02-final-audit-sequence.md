# 第二章最终审计执行顺序

状态：PREPARED_ONLY。等待父任务明确锁定最终 artifact ID、PDF SHA、当前 job 与批准计划；本清单不触发 API、编译、任务操作或中间稿看图。第三部署前失败的累计 18 页 PDF 不作为最终审计对象。教师验收保持 NOT_RUN。

准备检查已执行：两个既有脚本 AST 语法检查通过；pdfplumber、pdfminer、Pillow 可导入；本地 Poppler 程序存在。未执行渲染脚本正文。renderer 脚本 SHA256 `59cdbe63cf26de461525cc4d2c394b3c5079f0aeac15d81e621fd4fcf54305f9`，evidence 脚本 SHA256 `da0b7df9162c62baa88cc4cc727b8bed066f2b7ebf423274d15d44d54bc8dc76`。Poppler 位于 `C:/Users/kuogai/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe`；正式运行时将该现存目录加入子进程 PATH，不下载或更换渲染器。

## 1. 锁定真实版本与当前回执

先用 SQLite `mode=ro`、`query_only`、只读事务核对 run `fd6736af6ef14be3839e019e86ca1e5c` 已回到 AWAITING_USER_REVIEW，指定 artifact 是当前 revision 的最新非 superseded lecture.pdf。当前批准 revision 2 的计划/审批 hash 应为 `7e9b8e62373d98616c6c6b722016615ac6f25d79af483a25d81445a15a934227`；如身份变化应停下重新定位范围，不能把另一计划默认为同一基准。

同步保存当前成功 job、checks.rerun_requested 来源事件、最新 feedback.reviewed 回执及所引用输入/响应文件 SHA。明确这两条反馈有没有逐项覆盖，状态、理由、实际证据和正文是否一致；不能把旧 job 的成功回执拿来代表本次。supported_improvement 进入修复后还应看到对修订稿的新评估，不能只凭旧 actionable 回执宣称闭环。若未调用反馈评估，应如实写未执行，不把普通空 issues 当作两条反馈均满足。

保存最终 PDF、实际 TeX、build_manifest、quality_report、编译日志和最新五节 checkpoint 身份。按 `created_at DESC,rowid DESC` 读取，复核 output hash、已批 plan/check identity、LocalRecovery CHECKED 候选 hash、最后审阅及编译 source_key。全部当前单元正文须真实进入最终源码；任何未核对的候选不能代替最终稿。

## 2. 冻结渲染与离线证据

复用 `render-frozen-lecture-audit.py`，输入父任务提供的准确 run/artifact/SHA，输出新建的最终版本专用目录。该脚本只读核对渲染前后当前身份，调用 Poppler 输出全部页面 PNG/text 与 SHA，保留 stdout/stderr；渲染完成状态只代表 ALL_PAGES_RENDERED，仍不是视觉通过。

随后运行 `prepare-ch02-post-feedback-audit.py`，输入同一 artifact/SHA、上述 render-manifest 和新的输出 JSON。它复核编译来源、五节合法候选、正文变化、18 个题解关联、10 个 PDF 实际回链和全部页文件 SHA，初始语义/视觉状态为 PENDING。若脚本失败，保留失败日志和已生成产物，先查真实身份/结构，不为得到 PASS 放宽断言。

示意参数（执行时必须填入父任务已确认的真实值；本文件不执行）：

```powershell
.venv/Scripts/python.exe reports/iteration4/render-frozen-lecture-audit.py --run-id fd6736af6ef14be3839e019e86ca1e5c --artifact-id PINNED_ARTIFACT --expected-sha256 PINNED_SHA --output-dir reports/iteration4/CH02-final-pages-PIN
.venv/Scripts/python.exe reports/iteration4/prepare-ch02-post-feedback-audit.py --artifact-id PINNED_ARTIFACT --expected-sha256 PINNED_SHA --render-manifest reports/iteration4/CH02-final-pages-PIN/render-manifest.json --output reports/iteration4/CH02-final-evidence-PIN.json
```

## 3. 优先核对实际修订与回归

进行三版本比较：61 请求 pre-feedback 完整稿；101 请求 pre-thirddeploy 失败但五节 CHECKED 的内容基线；最终锁定稿。输出逐单元实际 diff，区分真实错误修复、教学改进、表达澄清及模型误报，不以修订次数代表质量。

1. S05.U18：原“以下答案与本节三道练习依次对应”已在 101 稿改成指向末尾答案区。核对最终句子、上下标题及真实排列仍一致，没有泄漏内部单元 ID；不要求为了不同但正确措辞继续改写。
2. S03.U14：保留正确直接比较解，新增正项极限比较 `a_n=(3n+1)/(n³+2)`、`b_n=1/n²`，比值趋于 3。检查正文、新增核算 AST、工具期望/输出一致。U14(2) 与 U16(2)/(3) 的参照比值为 1，不能机械统一为 3。对数例的起点须为 2。
3. S02.U10：原线性组合反证本来有效，现部分和展开若保留应正确；不得把这次表达澄清记作发现数学反例。
4. S04.U03：m=1 单独处理，含 `2m−2` 末项的偶数部分和展开从 m≥2 使用。连同 U07–U13 七个旧转义问题逐个检查，不能只查看 U07。
5. 逐项反馈引发的其他改动逐一核查题目条件、解答、证明依赖和工具请求；未变单元的关键证明仍作完整语义核对，不能只看新句子。

## 4. 原稿 16 项与批准范围完整核对

保留原始 16 项分母，逐项写最终正文证据、结论和范围差异。以下是待核查内容，不是预先判定 PASS。

| 原稿项 | 重点与现有定位 |
| --- | --- |
| D01 级数、通项、部分和 | S01.U01–U03；有限和、无限级数和有限实数极限的区分。 |
| T01 一般几何级数 | S03.U09–U10；完整参数 a=0、负公比是否真的覆盖。原批准正项参照的窄版本正确时，记范围部分覆盖，不误判数学错误。 |
| P01 部分和与望远镜 | S01.U07–U09/S03.U10；S3=3/4 是否只回答原题，完整望远镜公式有无新增。原稿范围差异独列。 |
| T02 通项趋零必要性 | S02.U02–U03/U07；部分和差证明、必要条件非充分及反例。 |
| T03 线性、有限改变与余项 | S02.U08–U14；线性只用两条已知收敛级数、有限首段合法性。 |
| P02 调和级数发散 | S02.U07；有限二进分组 `H_(2^m)≥1+m/2`，不靠无限项重排偷换。 |
| T04 非负级数准则 | S03.U01/U03–U04；单调部分和、有界与收敛的双向条件。 |
| T05 比较判别 | S03.U05–U06/U14/U16；比较方向、正倍数、有限首段。 |
| T06 p 级数 | S03.U09–U10；p>1 与全部 p≤1，特别 p=1 及 p≤0。 |
| T07 极限比较与积分 | S03.U07–U08/U11–U14；最终正项条件、有限正比值、积分端点及真实应用。 |
| D02 绝对与条件收敛 | S04.U06、S05.U02–U03；原级数收敛与绝对值级数是否收敛分别说明。 |
| T08 绝对收敛推出收敛 | S05.U04–U05；先由比较证 Σ(a_n+|a_n|) 收敛，再减 Σ|a_n|，不循环依赖待证命题。 |
| T09 莱布尼茨与余项 | S04.U02/U04/U07；从首项不增与所有 n 的界是否一致，`|R_n|≤b_(n+1)`、符号及合法指标。 |
| P03 奇偶部分和证明 | S04.U03/U07；m≥2 的差式、m=1 基础项、奇偶同极限、S0 使用是否有定义。不能因最终未用 S0 就要求另造定义。 |
| E01 分类、误差及反例 | S04.U06/U11–U12、S05.U11/U19–U21；n=999 是给定充分界的最小数而非实际误差最优；`1/(2·3^n)` 与 n=4；条件与绝对收敛级数相加证明。 |
| X01 例练与对应答案 | 每个题目恰有一个正确解答，题面和解答小问一致，末尾答案不缺漏；现基线 8 例、10 练、18 解，仅作身份核验而非质量分。 |

## 5. 真实 PDF 链接与全部页面

解析 PDF annotation/named destination 和实际 .aux，逐个记录全部 10 个练习答案回链的显示题号、答案页、目标锚点与原题页；不得只统计 10 个 link 对象。确认 18 个 example/exercise→solution 关联，无重配、漏答或只含标签不含解法。页码随最终重排，以本版为准。

逐页打开全部最终 PNG，每页保留页号、图片 SHA 和实际观察。检查中文缺字、公式上下标/分式/求和下限、边界裁切、重叠、断裂、跨页证明或题解接续、未解析 `??`、标题与答案区导航。重点查看 S03 新比值、S04 索引/不等式、S05 三题及全部末尾答案，但不能用重点页代替全页查看。不沿用旧 17 页审读或中间 18 页编译结果作为最终视觉验收。

## 6. 形成有界结论与保留失败

最终输出 MD + JSON，分列 mock、真实 API 产品记录、实际 Windows 编译、离线链接/符号核算、agent 逐页图像审读、教师数学/视觉验收。复用已有编译时标“产品已执行，本审计未新增”，不称新增编译。记录当前 quality_report 原状，特别 math/policy NEEDS_REVIEW 不可悄悄改为整体 PASS。

报告同时列已落实反馈、仍有的批准范围内问题、原稿与批准范围差异、可选风格建议及模型局限。无实际发现时不臆造新问题；发现确定问题则给准确 unit/正文/页码证据交父任务，保留固定版本，不手改讲义或自行反复抽样。所有未执行项如实 NOT_RUN。
