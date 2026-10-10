# 完整第三章的实际应用链验收

**PASS：任务 `e19924249d254adaa665752ed66504dc` 已到 `AWAITING_USER_REVIEW`，等待真实教师逐页审核。**

输入为原始 `第三章/大学数学（一）(1).tex`，完整 7 节、104 个来源单元。通过真实 `Service.attachments` 上传、`Service.propose` 和 Worker 生成计划，再由 `benchmark_driver` 通过 Service 确认当前版本及哈希，最后由 Worker 构建。未直接调用转换器代替应用工作流；未启动 TCP 服务，未使用 8765/8766。

| 验收项 | 实际结果 |
| --- | --- |
| 模板 / provider | 原始 FDU 主题及适配层 / mock（Beamer 确定性转换） |
| Windows XeLaTeX | PASS |
| 来源保真 | PASS |
| 逻辑 frame / PDF 物理页 | 93 / 108 |
| 全页渲染 | 108/108 |
| 下载接口 | 124 个产物均 HTTP 200，SHA256 与数据库记录一致 |
| PNG 下载 | 108/108，物理页连续完整 |
| 节检查点 | 7 |
| 数学 / 版面 | NEEDS_REVIEW / NEEDS_REVIEW，无 blocking issue |
| 模型请求次数 | 0，真实 API NOT_RUN |
| 教师审核 | NOT_RUN，数据库无审核记录 |
| 原始参考文件 | 53 个文件 SHA256 保持不变 |
| 运行期间代码变化 | 无；导入前后及运行前后哈希一致，完整 Python 源快照已保留 |

完整结果、逐产物下载哈希、源码快照哈希和每个 ZIP 成员见 [report.json](report.json)。API 下载副本位于 `downloads/`，任务数据库、原始上传、准备副本、编译日志、源码、PDF 与逐页图像位于 `workspace/iteration2-full-beamer-app-v2`。任务停在待审核状态，没有代替用户提交人工审核。

本次通过输入选项明确选择从完整原稿补齐真实书目。`NCBIEnzyme` 来自全稿第 12435–12436 行，`BradyWeil` 来自第 12424–12425 行；原始条目、来源行、原稿哈希和条目哈希都进入计划确认内容。输入 TeX SHA256 为 `73f3c32c19af46bf3c9b3e2881b18327a1aa8970ad2ff8bc2610d979ef655f3f`；全稿 TeX SHA256 为 `f73bb3c88540f4470ddf08881622cb014ee2904c4a03f551ad06fe2a1db7cb8d`。

下载的源包包含 `slides.tex`、原主题 `.sty`、FDU logo PDF、两份适配文件和 README。成员哈希与 `build_manifest.json` 逐项一致，不含 `.log`、`.aux`、数据库或环境文件。另从**实际下载的 ZIP** 安全解包到全新目录并执行 Windows 干净复编译，结果记录于 [zip-recompile.json](zip-recompile.json)。

首次执行揭示并修复一个 Windows 特有的实际缺陷：`Service.attachments` 对已有 CRLF 的补书目文本再次 `write_text` 换行转换，造成 1700 个 `CRCRLF`，使 `\mdfdefinestyle` 参数插入空段落。首个任务 `ebb23af8d8d54fe490a8dd31bfb60df4` 正确停为 BLOCKED，FID 虽为 PASS，编译仍失败且无 PDF。其日志、产物、输入、审批和代码快照完整保留在 `workspace/iteration2-full-beamer-app` 及 `reports/iteration2/full_beamer_app`。

修复为精确 UTF-8 字节写入。新增 CRLF 字节保真回归先失败，修复后与已有书目集成测试共 **4 passed**，包含真实 Windows 编译和 `\bibcite` 解析。第一次小编译夹具自身缺 `xcolor`，该失败产物仍保留；补齐夹具依赖后复测通过，未新增软件依赖。为保持审批完整性，未修补旧任务的已批准输入，而是重新上传原文件、新建并确认本次 v2 任务。

本报告是完整章节应用接线和文件交付验收，不代表真实 API 教学内容质量或教师视觉验收；六组直接转换基准报告没有被改写。
