# 编译失败局部恢复候选：20 项通过，尚待合并

2026-09-20。候选没有改运行产品、真实任务或已有讲义。真实 API 0；模型均为本地替身。最终候选 **20 PASS / 10.17 秒**，其中 19 项离线逻辑/mock，1 项为实际 Windows XeLaTeX 的“失败→局部修改→重新数学检查/模型审阅→新目录重编译通过”。教师数学与视觉验收 NOT_RUN。

## 修复的流程缺口

旧 `_lecture_sections` 在数学修订循环退出后才编译，真实 CH03 S05 遇到 `OVERFULL_BOX 0.5104pt at lines 932--933` 即结束。单纯追加局部修复预算不会让编译结果回到修订流程。

新候选在本节数学/内容/模型检查没有阻塞后编译。若每个 blocking 编译问题均能精确定位为当前节某个实际单元的 OVERFULL，记录失败源码/日志/PDF 和 hash，送入既有 LocalRecovery 与 LocalPatch；沿用同一预算、提案/拒稿计数和作用范围。修后重新检查数学、模型、引用，再在新目录编译。成功后才写 CHECKED。无法定位、跨单元、前节单元、外部文件、无行号或非排版编译故障保留原失败，不扩成全节重写；没有调低门禁或忽略小溢出。

定位使用实际渲染 `% UNIT` 标记与诊断完整行区间，并核验该诊断在真实日志对应行。重复/未知标记、跨 section/答案标题、外部输入歧义均拒绝自动定位。末尾搬移答案按实际渲染位置定位，不按原 JSON 顺序猜测。

每次失败都会将源文件、compile.json、日志、已有失败 PDF 和定位记录 hash 绑定到局部恢复证据链。接受的修改仍为未检查候选；旧失败文件不覆盖。`pending_compile_layout` 持久字段保持实际编译疑点，只有实际重编译通过才清除：即使补丁请求中断一到两次、恢复后模型只给普通 review，也继续禁止容差、缩字号或缩放绕过。

`reject_layout_suppression` 拒绝用于修改目标的 hfuzz/vfuzz、hbadness/vbadness、tolerance、emergencystretch、small/tiny、字号/缩放、全局宽度等命令。数学内容保真继续由严格目标范围、完整单元比较、数学/模型复审共同检查；本候选不是自然语言语义等价证明器。

## 合并文件与检查契约

- [compile-recovery.patch](待合并/compile-recovery.patch)：原 pipeline 的窄差异及新增 helper；**不要用整份 candidate 覆盖缓存刷新代理的 pipeline**。
- [compile_recovery.py](待合并/compile_recovery.py)：新辅助模块。[pipeline-compile-recovery.py](待合并/pipeline-compile-recovery.py) 仅供审阅候选行为。
- [SHA 记录](待合并/compile-recovery-source-hashes.json)：原 pipeline `350f9eff0d4a8f24937e4c0dfc605f7f2bb928fc603b313d99219553ea628a1c`；候选 `7691bc8524f1ae329030560df3e7b4e75070904b1e5e323c2d26ea42dd955e68`；helper `aad2764ca6751343fb79b4e29ced6822a245584b1782185d928f727b8e3c63ab`。最终复核时原 pipeline 未变，helper 与测试版本一致。
- [test_compile_layout_recovery.py](../../tests/test_compile_layout_recovery.py)：新增回归；正式合并后应直接对真实产品加载重跑。

**合并时必须把 `compile_recovery.py` 加入 `_section_check_contract` 的 `modules` 元组。** 新 helper 后续单独修改也要触发旧 CHECKED 重查，不能只靠这次 pipeline 文件变化偶然失效。

## 已执行证据

| 验证 | 结果 | 边界/证据 |
|---|---|---|
| 第一轮隔离 mock | 13 PASS / 3 FAIL / 1 deselected | 候选 `__file__` 指向报告目录，导致寻找未改的 lecture_fragments.py 失败；[失败日志](compile-recovery-candidate-mock-01.log)保留 |
| 修正隔离加载器依赖路径 | 16 PASS / 1 deselected | [mock-02 日志](compile-recovery-candidate-mock-02.log)；只改候选加载器依赖定位，没有弱化产品断言 |
| 首次真实小 XeLaTeX | 1 PASS / 16 deselected | [windows-01](compile-recovery-candidate-windows-01.log)；长 mbox 原文保留字词、去掉不可断行框后成功，模型为替身 |
| 最终全部候选专项 | **20 PASS，10.17 秒** | [日志](compile-recovery-candidate-final.log)、[JUnit](compile-recovery-candidate-final.xml)；包含新的一次/两次中断恢复后拒绝 hfuzz 和外部同名 lecture.tex 边界 |
| 真实旧 CH03 U22 只读定位 | **PASS：仅 S05.U22，源码 932–933，日志 635** | [机器证据](compile-recovery-real-U22-mapping.json)；实际源 hash `17e3a09495be8fbe8e39abdff18a7ecd88ba52d68f55f926153bdac9246e3800`；旧失败源/日志均未改 |

不累加重叠专项。实际 Windows 用例包含原失败 PDF 与成功 PDF，不能把两个编译都说成成功。真实 CH03 U22 本次只定位，**未替它调用模型修复、未重新编译完整章、未做页面视觉检查**。完整产品回归和合并后的真实任务恢复由主任务执行。
