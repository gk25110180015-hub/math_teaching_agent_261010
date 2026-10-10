# 解析与 Beamer 模块的早期阶段证据（历史记录）

本文件保留实施初期的真实失败/依赖状态。后续最终33项离线回归、实际PDF和矩阵结果见 [reference_implementation_tests_final.md](reference_implementation_tests_final.md)，不得将本文早期NOT_RUN当作最新状态。

环境：Windows 本机，工作目录为新工程 `math-teaching-agent`。未修改第一章/第二章/第三章原件。下列测试均未调用真实供应商。

## M0

执行 `D:\anaconda\python.exe scripts\audit_references.py`。沙箱内写新报告目录得到 PermissionError；保持原错误事实，申请仅运行审计脚本的沙箱外执行后成功生成清单和 6 个要求报告。

实际结果：51 个文件；三份同名讲义以数据集区分；全部字面 TeX/sty 本地依赖及显式宏包定位成功；3 份 FDU 文件同一 SHA-256 `98d46f69b226ebf615e428d2895473aacc90ab9483df62ee78358e6d5bfedf43`。导入时 PDF 渲染、字体几何、教师审阅 NOT_RUN；相应基准数字为 null。

## M1、M3、M4 的离线逻辑测试

先建立 `tests/test_parsing_beamer.py`，执行时得到 `ModuleNotFoundError: math_agent.parsing`（实现前失败）。实现后第一次执行实际为 `12 passed, 1 failed`，失败是 T52：`\openin0` 被命令边界漏过。修复边界后实际 `13 passed`。随后增加 verbatim、长证明完整段落拆分和指定位置新增的回归，运行结果 `16 passed in 0.08s`。

实际命令：

```powershell
$env:PYTHONPATH = 'src'
& 'D:\anaconda\python.exe' -m pytest tests/test_parsing_beamer.py -q -p no:cacheprovider
```

覆盖内容：明确授权删除题解；自定义 theorem 原始区间及关联；标准数学宏；实际输出公式/正文篡改失败；四档字号；ZIP 越界/执行附件；危险 TeX；不透明内容保留；verbatim 内容；长证明完整语句/段落顺序；新增内容指定 section。

这 16 条是 mock/unit 层逻辑结果，不是 Windows PDF 排版、真实 API 或教师视觉通过证据。M4 字号/拆页当前为可配置候选和保守文本启发式，最终仍需实际编译测量。

另执行真实 CH01 讲义只读解析：12 个非空 section、136 个内容单元、解析问题列表为空。该结果不等于数学内容或两版逐单元忠实度审校通过。

## 待执行的编译探针

`scripts/probe_beamer.py` 会以真实 XeLaTeX 编译两个模板、渲染全部页并保存分模板 result.json。首次尝试前环境检查 `.venv` 未装 pytest/pypdfium2，故当时未执行探针；依赖安装完成后继续运行。实际后续状态以探针 result.json 及最终验收报告为准。

真实 API：NOT_RUN。教师人工视觉验收：NOT_RUN。原生 TeX 模式是 trusted_local，静态预检不是完整操作系统沙箱。
