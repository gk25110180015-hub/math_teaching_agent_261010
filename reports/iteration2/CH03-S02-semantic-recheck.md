# CH03 S02 局部数学与恢复状态复核

2026-09-19T19:41:59.664Z。Run：`a45be503af594ce8aae0bb1e4c30184b`。

**两次修复数学上成立，已读检查点与修后候选一致；教学组织仍有不足，不以编译通过替代教学质量判断。整章 PENDING_OUTPUT，教师验收 NOT_RUN。**

本次为独立AI文本审读、只读程序比较和本机真实SymPy核算；0 API，不改数据库、原稿或产品代码，不重新编译。

## 实际修改及保真

| 修复 | 改动单元 | 完整对象未变的单元数 | 其余变化 |
|---|---|---:|---|
| repair-1 | U01 | 12 | 补齐夹逼的函数定义域、有限共同极限L和明确结论；数学内句号仅按已记录span改为text字体 |
| repair-2 | U02、U03 | 11 | 新增C01→U09计算请求及一条核算局限说明 |

各次ID、顺序、kind、relates_to保持，before/after哈希均吻合。repair-1 raw与归一化对象不完全相等：唯一格式变换为“。”→`\\text{。}`，已按span精确重放确认；不是数学内容改写。repair-2 raw与归一化完全相同。

原calculation列表为空，repair-2追加一项约分后x+1在x→1的双侧极限请求。因此不能声称所有metadata或calculation列表完全不变；具体差异保存在JSON。

## 数学核对

### CH03-S02-R1 夹逼引入陈述补全

单元：S02.U01。原稿未声明h在邻域内有定义，也未明确共同极限及结论。repair-1明确f,g,h共用去心邻域，有限共同极限L，并写出lim f=L。命题成立。

### CH03-S02-R2A 四则运算证明补足且无循环

单元：S02.U03。和用两误差ε/2与共同δ；负函数误差恒等式支持差。先用误差1建立|f|<|A|+1，再取M=|A|+1>0，控制|g−B|<ε/(2M)和|f−A|<ε/[2(|B|+1)]，与局部界的δ共同取min。A或B为0仍成立。

### CH03-S02-R2B 倒数与商的关键绝对下界正确

单元：S02.U03。B≠0给出最终|g−B|<|B|/2，反三角不等式得到|g|>|B|/2。再取|g−B|<ε|B|²/2，倒数误差≤2|g−B|/|B|²<ε，乘以f得到商法则。不是只由g非零直接套未证商法则。

### CH03-S02-R2C 复合极限穿孔与定义域条件齐全

单元：S02.U02、S02.U03。g→b、f(t)→L，同时要求相关去心邻域内g(x)≠b且g(x)属于f定义域。证明取r保证不等于/有定义，外η与内δ连接，取min(r,δ5)得到0<|g−b|<η，因此可用外函数的去心极限。

若删去g(x)≠b而不补f(b)=L，可令b=0、g(x)恒0、f(0)=2而f(t)=1(t≠0)：两个基础极限为0和1，但复合恒2。这说明现有额外条件有实际数学作用。

最终避开b是此版本的充分条件；若外函数在b连续，可允许取到b。现文未声称该条件对所有复合极限都是必要的，因此没有过度结论。

### CH03-S02-SQUEEZE 夹逼定理与误差结论正确

单元：S02.U04、S02.U05。两侧同一有限L、共同去心邻域中h≤f≤g，取共同误差邻域得到L−ε<h≤f≤g<L+ε。证明默认在假设的共同邻域内取δ；若要把这个约定写得完全显式，可同时与该邻域半径取min。当前不判定为结论错误。

### CH03-S02-EXERCISES 已有例题/练习计算正确

单元：S02.U08、S02.U09、S02.U10、S02.U11、S02.U12、S02.U13。约分保留x≠1，极限2；二次多项式在2处极限0且不能套严格保号结论；练习分子极限1、分母3≠0，商为1/3。题解关系均保持。

## 仍存教学不足

- **warning / S02.U01、S02.U04**：U01标definition，但实为夹逼定理完整陈述；U04再次重复同一命题。数学无错，术语引入与定理单元的分工不清晰。
- **warning / S02.U02、S02.U03**：一个thm:limit-algebra单元同时承载四则运算与另段复合极限，证明也较长。复合假设明确，因而不是数学错误；独立标签/标题能改善教学引用和阅读。
- **advisory / S02.U08、S02.U10、S02.U12**：例题/练习均偏代数变形和四则运算，夹逼与复合只有述证，缺少专门应用训练。批准目标强调运用夹逼思想计算，现有训练支撑较弱；这不是凭关键词断定定理缺失，也不追加“每个定理必须有题”的硬要求。

## 检查点、编译与核算

SQLite以 `mode=ro` 和 `query_only=ON` 读取，未初始化Store或执行迁移/写操作。

- section.S02输出哈希：`2584772cefafb730199dd2a3516512e312c08f0a2495b7a35ff7a3720ba60a11`，与payload重算一致。
- generated哈希：`f99d591de59dbcd1cc5e0d711d7e8c4c6593b0709290786fe3f04dc035809561`，完整对象等于repair-2。
- 编译源哈希：`9c83a54709353973de2b9925cf14c1ba9d626d15955a057e6bf737b107331bb3`，与检查点source_key文件一致。
- 引用检查PASS，pending_labels为空。
- 既有Windows XeLaTeX：PASS，2遍、6页；这是S01+S02累积稿。
- PDF SHA-256：`fa090a372a81aac343526c284aba32c777dfe4c45b1250e70bf83b3a47439e0e`，已核验。

本次实际重跑JSON AST：C01返回2，`symbolic_check_passed`。它只核算约分后表达式，不能证明x≠1约分前提、四则定理或复合定理。一般证明为AI文本审读，教师/人工视觉验收均未执行。

源码定位：U01 L139、U02 L151、U03 L174、U04 L214、U05 L232，以证据源码哈希为准。

## 证据文件

| 文件 | SHA-256 |
|---|---|
| [candidate-normalized.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/sS02_f4c6b3226390/candidate-normalized.json) | `0a68b775b071d60e9b9189a9437e057de949be8c499c49ce750feaa779936658` |
| [repair-1.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/sS02_f4c6b3226390/repair-1.json) | `4a8261e833d6ac456db892b5ddb39bf06e276d09be368b02c9008ef68d690020` |
| [repair-1-raw.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/sS02_f4c6b3226390/repair-1-raw.json) | `6721d3e52f3ae4e0b342f489c52dde73c19d6d3c66f5818522a0f232d28ba255` |
| [repair-1-normalization.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/sS02_f4c6b3226390/repair-1-normalization.json) | `4f38d5cf156dcaaad8f266c58ce6631e61295fb0b6d14a0d6b76f53e53876f1b` |
| [repair-2.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/sS02_f4c6b3226390/repair-2.json) | `19581b63844e84cd14edd474d9e84f4d89176122d2d191dfd04b1a8676a10a30` |
| [repair-2-raw.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/sS02_f4c6b3226390/repair-2-raw.json) | `1f150ebb50ea7d152a53def24f76689146bd11b34ebbb7b6c00f8c3de4da2512` |
| [repair-2-normalization.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/sS02_f4c6b3226390/repair-2-normalization.json) | `4f71f74e0dfbe3f350506477cde43362118fd06844caf6e2c00a8fb7b992ed9a` |
| [review-0.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/sS02_f4c6b3226390/review-0.json) | `e1cf68497909d8b7096445b01ab89cf073a798d81a2f590eea45179f95bc46ab` |
| [review-1.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/sS02_f4c6b3226390/review-1.json) | `01c0bd2bd2aee36532831528c7944e98303da6e831aafe2e48cf4fc40fc8abf9` |
| [review-2.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/sS02_f4c6b3226390/review-2.json) | `b4620a2c1956ba4e5322081d697c56304f9ab56e355f44cbfd7c4e789727325c` |
| [compile.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/sS02_f4c6b3226390/compile.json) | `dc75debbf7f01bc01d9ee6c5e276871f9f1bb45cb78b4a335d870ee5a9a23856` |
| [source/lecture.tex](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/sS02_f4c6b3226390/source/lecture.tex) | `9c83a54709353973de2b9925cf14c1ba9d626d15955a057e6bf737b107331bb3` |
| [build/lecture.pdf](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/sS02_f4c6b3226390/build/lecture.pdf) | `fa090a372a81aac343526c284aba32c777dfe4c45b1250e70bf83b3a47439e0e` |

## 审计过程说明

- 首次离线断言假定raw==normalized，对repair-1失败；检查发现仅句号到text字体的已记录变换，随后按精确span重放核验通过。此为审计假设修正，不是数学内容被删改。
- 首次沙箱内SQLite SELECT返回unable to open database file；以同一mode=ro/query_only做获准本机只读访问后成功。没有初始化Store、迁移或写入数据库。

