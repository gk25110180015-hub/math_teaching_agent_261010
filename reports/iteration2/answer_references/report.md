# 末尾答案定位与回链

`render_lecture` 现在为每道练习插入程序保留标签 `mathagent:exercise:` 加 `SHA256([section_id, unit_id])`。移到讲义末尾的解答标题显示“练习 1.2 的解答：”并整段可点击，返回对应练习。跨节相同 unit ID 也生成不同标签；正文占用保留前缀时明确阻塞，避免标签冲突。

原始单位正文、数学、ID、关联保持不变。例题解答仍在例题后显示“解：”；选择各节内放答案时也保持原有位置与标题。修改仅影响之后生成的文档，没有重建现有五页真实 API 稿，没有写入其数据库或审批产物。

测试先红：2 failed / 1 passed / 1 Windows test deselected。最终 `test_answer_references.py` 与现有 CRLF 回归共 **6 passed，4.41 秒**，其中实际 Windows XeLaTeX 编译、aux 编号、PDF 链接和可见标题检查均通过。夹具为两个章节、两道练习和一道含内联解答的例题；两条回链分别指向练习 1.2、2.1。模板共用 `definition` 计数器，所以实际 PDF destination 为 `definition.1.2`、`definition.2.1`；最初测试误假设 `exercise.*` 已修正，失败目录保留。

实际编译 PDF 1 页，1/1 渲染，几何检查 PASS。实现者已检查渲染图：两条答案标题清楚显示蓝色可点击编号，练习与例题解答位置正确，无可见截切。此为**agent 视觉检查**，教师人工验收 **NOT_RUN**。本项 API 调用 **0**。

证据：`compile.json`、`evidence.json`、`pdf-check.json`，以及此目录的 `lecture.tex`、`lecture.pdf`、`lecture.aux` 与编译日志。环境代理已收到稳定通知，负责和最新全局修复逻辑合并后的定向验收。
