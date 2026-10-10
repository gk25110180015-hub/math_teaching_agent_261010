# 编译、PDF 与数学检查验证记录

本记录只报告实际执行证据，不替代 M2/M4/M5 整体验收。原始参考资料未修改。

## 实现

- `src/math_agent/compiler.py`：绝对 XeLaTeX 路径验证；过滤工作目录伪编译器；源码安全预检；只读源快照到全新构建目录；白名单子进程环境；禁 shell escape、`openin_any=p`/`openout_any=p`；2–4 轮辅助文件稳定检查；所属进程树取消；每轮日志及结构化错误；不复用旧 PDF。已知 overfull 为阻塞，保留本次新 PDF 供草稿诊断。
- `src/math_agent/pdfcheck.py`：PDF 打开及全页渲染均在无密钥子进程；pypdfium2 PNG、SHA-256、pdfplumber 几何；`.nav` 物理页/overlay 映射必须恰好覆盖 PDF；不根据 pause 次数猜页数；逐页风险及人工审核状态。
- `src/math_agent/mathcheck.py`：受限 JSON AST 白名单；显式变量假设；最多 256 节点/20 层，8 秒单项/60 秒单节；无密钥子进程；等价、导数、极限、级数收敛性、数值抽查；UNKNOWN 不当作真；空复算清单为 NOT_RUN / NEEDS_REVIEW。

## 锁定环境最终验证（2026-09-20）

项目 `.venv` 中实际版本：Python 3.12.4、pypdfium2 5.13.0、pdfplumber 0.11.10、SymPy 1.14.0、pytest 9.1.1；实际引擎 TeX Live 2024。

```powershell
& .venv\Scripts\python.exe -m pytest tests/test_compiler_pdf.py tests/test_mathcheck.py --basetemp workspace\compiler_math_locked_final -q
```

**21 passed in 29.86s**，日志 `reports/compiler_math_locked_final.log`。随后针对源 ZIP 的 README.md/.txt 支持新增回归并单独运行 **1 passed, 11 deselected**，日志 `reports/compiler_bundle_docs.log`。

- 已实际编译中文目录和文件名 `讲义 (第一章).tex`，稳定编译不少于两遍；新 PDF 可打开，两张 overlay 物理页全部渲染；nav 映射准确覆盖所有物理页。
- 已实际生成三 overlay 的中间页溢出 fixture；三页全部渲染，第 2 页实际越界文本由几何检查标为 blocking，不能因第 3 页正常而漏检。
- 已实测故意编译失败不返回旧 PDF、取消无限循环只终止所属树、`openout_any=p` 拒绝工作区相对越界写入。
- 数学测试增至 10 项：合法交错级数判别不误报；`x/x=1` 不得在未声明 `x!=0` 时因约分而丢失定义域。
- 两张成功合成 PDF 页已由实现者查看，题目在两 overlay 中位置稳定，未发现该两页可见裁切；图像证据在 `reports/compiler_visual_evidence/`。这不是教师人工视觉验收，也不是三章验收。

首次锁定环境跑出 20 passed / 1 failed 的日志仍保留于 `compiler_math_locked_initial.log`：最初 T47 fixture 在同一段插入大 vspace，仅产生空白溢出而未让文字越界，检查器没有错误地报告文字越界。对其实际 PNG/坐标核查后，修正 fixture 的段落边界以制造真实越界；没有放宽断言。原问题页为 `reports/middle-overlay-debug.png`；修正后的专测 `compiler_middle_overlay_corrected.log` 通过。

所有成功/失败测试的 TeX、每轮日志、PDF、全部 PNG 保留于 `workspace/compiler_math_locked_final/` 及较早独立目录。未触及三章原件。

真实 API：**NOT_RUN**。教师人工视觉验收：**NOT_RUN**。本报告不声明隔离沙箱实现或三章双模板通过。

后续集成发现的两项诊断修复：

- 真实长源中的 `Incomplete \\iffalse`、`.vrb` 的 `LaTeX Error` 现在有单独 fatal 规则与精确源行。先红后绿日志为 `compiler_fatal_location_red.log` / `compiler_fatal_location_fixed.log`（后者含实际故意失败编译，共 2 passed）。早期 warning 不再掩盖最终致命原因。
- 一次中文路径回归出现瞬时 `COMPILER_PROCESS_ERROR`，原 pytest 摘要截断了具体异常；失败日志与构建目录保留，不能据此确定唯一根因。资源统计代码确有“扫描与 TeX 临时辅助文件原子重命名竞争”的问题，现容忍扫描时已经消失的文件，并增加可重复的消失文件 fixture；今后的进程异常另存完整脱敏 `pass-N.process-error.json`。修复后的中文编译、3-overlay 中间页越界、指纹失效和 fatal 定位等 5 项定向回归通过，日志 `layout_final_regression_fixed.log`；先失败 fixture 日志 `compile_size_race_red.log` 保留。

## 早期基础环境执行记录

2026-09-19 使用本机 Python 3.12.4（Anaconda）与 SymPy 1.12，以及绝对路径 TeX Live 2024：

```powershell
$env:PYTHONPATH='src'
& 'D:\anaconda\python.exe' -m pytest tests/test_compiler_pdf.py tests/test_mathcheck.py -k 'not compile_chinese_path_and_all_overlay_pages and not middle_overlay' --basetemp workspace\compiler_math_base_verified -q
```

结果：**17 passed, 2 deselected**。日志 `reports/compiler_math_base_verified.log`。

| 分类 | 结果 | 证据 |
|---|---|---|
| 编译安全/映射离线单元 | PASS（6） | 环境无密钥、输入目录伪引擎、旧 PDF、TeX 危险读写、信任确认、nav覆盖 |
| 数学核算单元 | PASS（8） | 故意错误级数/量词/定义域、导数与极限、假设未知、调和级数、数值不升级证明、拒绝代码/巨大指数、子进程无密钥 |
| Windows 实际故意失败编译 | PASS | 未定义命令明确失败、PDF 不返回，保留日志 |
| Windows 实际取消 | PASS | 无限循环 TeX 按取消停止；同时运行的其他 Python 进程仍正常 |
| Windows 实际越界写入探针 | PASS | 绕过预检直接测试 `openout_any=p`；拒绝 `../escape.txt`，没有越界文件 |
| 成功 PDF 与全部物理页渲染 | NOT_RUN（此记录时） | 等项目虚拟环境的 pypdfium2/pdfplumber；两条专用测试已编写 |
| 真实 API | NOT_RUN | 环境无密钥、未启用；这些测试完全不访问供应商 |
| 教师人工视觉验收 | NOT_RUN | 不把自动化或图像生成视为教师审核 |

先写失败 fixture 再实现的日志：`compiler_red_phase.log`、`mathcheck_red_phase.log`。中途发现并修复 TeX `\openin1` 命令尾接数字时正则单词边界漏检；原失败日志留存。系统默认 pytest 临时目录权限失败日志也留存；后续统一使用项目 workspace 下独立 `--basetemp`。

## 边界

- 可信本机模式不是文件系统/网络隔离沙箱；`isolated` 未实现，不宣称通过隔离验收。
- 几何只能发现所实现的风险；正文安全区现有匹配模板指纹和引擎的实际 measured_probe（详见 `layout_probe_validation.md`），仍非完整校准，PDF 几何 PASS 不代表人工视觉 PASS。Beamer 隐藏 overlay 的严格同帧可见对应诊断及真实溢出反例见 `pdf_overlay_visibility_validation.md`。
- 四档字号需与来源/渲染静态检查共同判定；自然数学上下标不按小字号违规处理。
- 数学工具只核算显式请求的支持表达式；没有通用定理证明能力，未覆盖内容须靠独立模型复核和教师审阅。
- 首轮使用系统基础依赖的记录保留供追溯；锁定虚拟环境完整重跑证据见上方，不混淆两个运行环境。
