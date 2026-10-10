# CH01 S02 两次局部修复复核

2026-09-19T19:10:42.564Z。Run：`05748ab6260c40989a560a98e1e2065a`。

**两次数学修复均确认有效，范围保真校验通过；本节教学覆盖仍为 PARTIAL，因为绝对值极限应用训练尚未落实。整章 PENDING_OUTPUT，教师验收 NOT_RUN。**

只读审查，API调用0，原JSON/TeX/代码均未修改；本次没有重编译或查看页面。

## 修复范围

| 步骤 | 唯一改动 | 完全未变单元 | 修复后 canonical SHA-256 |
|---|---|---:|---|
| repair-1 | S02.U11 | 14 | `6a8b02ce84453be82ad732b0343b24903ba70c7b13e121ae594dde538e7c8786` |
| repair-2 | S02.U09 | 14 | `9cba9315f447cc7312aed6e239ebfb3d0fc73e5e400fad229673f80c6c9f4e17` |

初稿→最终共改 U11、U09，其他13个单元完整对象一致。逐次before/after哈希均吻合记录；ID、顺序、kind、relates_to与所有calculations/limitations/uncertainties等section字段保持。两次raw响应均与归一化后的section一致，repair-2完整保留repair-1的U11修复。

## repair-1：U11 倒数与商法则

因M≠0，|M|/2>0。对b_n→M使用极限定义，得到最终|b_n−M|<|M|/2；反三角不等式给出|b_n|≥|M|−|b_n−M|>|M|/2。

于是|1/b_n−1/M|≤2|b_n−M|/|M|²。给定目标误差η>0，再把|b_n−M|控制到η|M|²/2以内，并取两个尾部阈值的最大值，可直接由定义得倒数极限。原文的“→0”在此可由一个误差项的定义展开，不依赖后续夹逼定理。

再用先前已建立的乘积法则，a_n(1/b_n)→L/M；M为负也成立，因为所有界使用绝对值。 商法则U10明确额外要求每一项b_n非零，比只在尾部有定义更强但合法；并非错误。

这次修复补上了原来从定性保号直接跳到定量绝对下界的论证缺口。

## repair-2：U09 常数倍、和与乘积

- c=0单独处理；c≠0使用ε/|c|，避免除零。
- 分别控制两列误差<ε/2，在max(N1,N2)后的同一尾部相加，直接得到<ε，不再借用正在证明的和法则。
- 先常数倍证明−b_n→−M，再用已证和法则，顺序无循环。
- 从已证有界性选择固定K>0，即使a_n恒零也可选正界。恒等式a_nb_n−LM=a_n(b_n−M)+M(a_n−L)正确。两项分别控制于ε/(2K)和ε/[2(|M|+1)]，得到误差<ε/2+|M|ε/[2(|M|+1)]<ε。
- M=0仍合法：|M|+1避免分母为0，第二项为0；K>0也避免除零。

新增证明正确处理共同阈值、c=0、M=0及K>0，不循环调用正在证明的和法则，也不借用尚未教授的夹逼定理。U11仍保持前次修复。

## 尚未落实的教学目标

批准计划明确要求“能够处理含有有理式、绝对值和常数倍的基本数列极限”。

U12只有3/n+2与(2n+1)/(n+3)；U14只有线性组合、乘积和商。正文未给出a_n→L⇒|a_n|→|L|的教学依据或含绝对值极限训练。

证明里的|a_n−L|等误差估计不等于学生已学习处理含绝对值的数列极限。 因而当前数学结论虽正确，本节不能评为教学覆盖完全符合。此项保留 **PARTIAL / warning**，不是对尚未产出的全章作缺失判定。

可后续补充反三角不等式对应的绝对值极限依据及实际训练；本次没有代写或修改已确认正文。

## 核算与编译证据

原JSON AST请求S02.C01→U13重新执行：实际本机SymPy返回2，证据类型symbolic_check_passed。另独立核算3/n+2、(2n+1)/(n+3)的极限均为2；练习三项为11、−2、−3。不是mock或API；少量计算不能替代一般证明。

既有worker Windows XeLaTeX编译：PASS，2遍，4页；PDF SHA-256 `422102320662c7aa9c95ce6385cf4ee898908945f261400be4c52c5bdd4416c1` 与文件核验一致。本次没有重编译或视觉验收。

生成TeX定位：U09 L127，U11 L137，U12 L141，U14 L147；以此报告列出的源码哈希为准。

## 文件证据

| 文件 | SHA-256 |
|---|---|
| [candidate-normalized.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS02_d764aedf5652/candidate-normalized.json) | `76b184748f4661fabfc6b37aa54ebb1b814ffa291c0a05093762fd66df994f05` |
| [repair-1.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS02_d764aedf5652/repair-1.json) | `a3db99f661683053d9ad2c602a8488d513284936d120400f28e9de894128189c` |
| [repair-1-raw.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS02_d764aedf5652/repair-1-raw.json) | `70d523b93b1c9eb6800eff19d728ce3fe292a4bf633250ca4bf1efafe35f1c70` |
| [repair-1-normalization.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS02_d764aedf5652/repair-1-normalization.json) | `d0d4c399ab8711cb8b3ad1bab018e57cf9684abca503f9874dae3749f9a5d3b3` |
| [repair-2.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS02_d764aedf5652/repair-2.json) | `50b27489e552bfc9d12accf26c7a83df81fee926da4c8a3e2f901363535f99ac` |
| [repair-2-raw.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS02_d764aedf5652/repair-2-raw.json) | `c483d16ad325069f8d65085c727c65a566fa3d1d3831e73b8c831e5ad9323991` |
| [repair-2-normalization.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS02_d764aedf5652/repair-2-normalization.json) | `1a0f08502aff603f3b37882533c0eac4c4ac62d09c65970e51a067f453a6bd51` |
| [review-0.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS02_d764aedf5652/review-0.json) | `ab66a2d4f663395e503fcc43755a4de584f6a1aa764cd437b7344d6ed8543bd7` |
| [review-1.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS02_d764aedf5652/review-1.json) | `137dba95240a616011dbdd2873ad3c1eb3aaa7670484f946a06fd1fa221ad179` |
| [review-2.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS02_d764aedf5652/review-2.json) | `ed9643ef4580102974bccadbe773adcb0d311051406fc1989a356a600f4b1c91` |
| [compile.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS02_d764aedf5652/compile.json) | `765949227daed41aaa400f399b56de93324855ff178bd68c9c6d77eb115712e1` |
| [source/lecture.tex](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS02_d764aedf5652/source/lecture.tex) | `8171c519f902166b99f31301c7e2b57e9e929d3c1bdc593a36e68f2303169ee8` |
| [build/lecture.pdf](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/sS02_d764aedf5652/build/lecture.pdf) | `422102320662c7aa9c95ce6385cf4ee898908945f261400be4c52c5bdd4416c1` |

