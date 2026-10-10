# M3：TeX、来源与双模板

实现保留原文跨度/hash的扫描器、嵌套环境/数学模式/注释/verbatim/条件隐藏区、输入依赖闭包、宏/自定义环境注册、题解关系、受控ZIP、未知单元保留。用户删改使用精确源ID/决策ID；输出独立按实际 TeX 片段验证顺序/公式/完整覆盖，新增也核对实际位置及正文，不相信模型填写的 source_map。

默认与真实 FDU 模板均接入。三章 sty 的同一哈希记录在 reference_index；原 sty 字节不改，独立字体/版式适配。缺资源/不同hash时阻塞，构建前复核审批时的主题hash，不静默换模板。

合成双模板真实编译、全部页/overlay：见 `workspace/beamer-probe/` 和 `reference_implementation_tests.md`。三章真实材料六组的独立来源核对已实际执行；最终状态、页数和问题以 `reference_matrix.md/json` 为准，不能把合成样例替代三章验收。

修复并保留证据：openin0危险宏边界、CRLF重复转换、source scaffold换行hash、solution环境重定义、iffalse跨frame、数学array被当顶层环境、长列表安全边界。原件51文件重复哈希核对无改变。

源文件缺少书目的引用、无法安全排版的片段不得删除来过检。保留原文、编译日志、草稿和审阅问题。无法可靠展开的 TeX 继续标 opaque，不宣称理解全部语义。
