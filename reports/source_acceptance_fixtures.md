# T07 / T09 / T31 有界验收证据

测试文件 `tests/test_source_acceptance.py`，Windows 本机实际执行 **3 passed in 2.70s**。其中 T07、T09 为离线逻辑；T31 为真实 XeLaTeX 编译。无真实模型 API 调用，无教师视觉验收。

- **T07 PASS**：两个不同 section 都有“例3”。断言ID、section名称、原文件行号不同；只明确删除第二个ID与它的solution_of关联解答，第一题及第一解仍在实际输出。此fixture验证定位候选和精确删除，不保证从模糊自然语言自动猜中用户意图。
- **T09 PASS**：引入文字与 `$x>0$`、`$a>0,a\ne1$` 必要定义域条件混在同一 intuition 单元。输出完整保留混合原文，独立保真检查通过；故意移除条件会失败。没有自动拆开或删除混合段落。
- **T31 PASS（阻塞行为）**：用户表格使用非法 tabularx 列格式 `QQ`。实际编译 **FAIL**，精确诊断 `./slides.vrb:9: Package array Error: Illegal pream-token (Q)`。源表格原文/source_map保留，来源FID PASS，失败日志和源文件落盘。此测试通过指正确阻塞、定位与保留，不表示表格编译成功或已自动修复。

持久产物：`workspace/acceptance-source-20260920-003600/test_T31_broken_tabularx_block0/`，含 `source/slides.tex`、`compile_result.json`、`build/pass-1.stdout.log`、`build/pass-1.tex.log`。首次指定的basetemp父目录不存在导致3个setup errors；之后改为workspace下直接目录再执行，未掩盖首次错误。

后续纯article布局命令空frame回归也先失败（30pass/1fail）再修复。当前parser/Beamer测试31项、加T07/T09共33项离线PASS，T31在单独真实Windows执行中PASS。源码数学内容不因分页命令迁移而删除，原布局单元在render.json的presentation_source_units保留原文/span/hash。
