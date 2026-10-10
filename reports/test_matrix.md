# T01–T60 验收索引与限制

本表按规范逐项区分证据范围；一个用例的合成通过不代表真实三章/真实API/教师审核通过。最终 pytest 数量及命令见 FINAL_ACCEPTANCE.md 和对应 JUnit。

| 用例 | 当前证据/状态 |
|---|---|
| T01 | PASS，API新建保存专题/难度，审批前无正文产物。 |
| T02 | PASS，问题末项CUSTOM，推荐项没有自动提交；浏览器真实点击。 |
| T03 | PASS，证明策略改变、其他选择保留。 |
| T04 | NEEDS_REVIEW，自定义文字作为可见约束进入哈希计划；自然语言比例未做通用定量语义验证，教师须核对产物。 |
| T05 | PASS，字号规则由程序固定，没有询问放宽字号。 |
| T06 | PASS，精确例题ID及明确关联题解获批删除，真实UI/实际TeX核验。 |
| T07 | PASS，两个同名“例3”夹具展示不同章节/行号/ID候选，只删除选中题及显式关联题解；任意自然语言重名解析未声称支持。 |
| T08 | PASS，模型自行approved/建议遗漏不构成授权，渲染拒绝。 |
| T09 | PASS，纯引入与定义域条件混合的具体夹具完整保留；篡改其中条件会导致来源检查FAIL。 |
| T10 | PASS，新增正文/位置/优先级持久化，真实TeX位置和数学内容独立核对。 |
| T11 | PASS，并发执行只入队一个job。 |
| T12 | PASS，真实undefined命令导致明确compile失败，审批仍在。 |
| T13 | PASS，原审批及通过的讲义section复用；真实UI失败重试不回确认。 |
| T14 | PASS，旧计划/问题版本409。 |
| T15 | PASS，SQLite重开、Windows脚本重启和真实worker崩溃后租约恢复；真实API崩溃计费边界NOT_RUN。 |
| T16 | PASS，旧fencing token拒绝提交。 |
| T17 | PASS，真实无限循环TeX取消，只停自己的进程树。 |
| T18 | PASS，HTTP MockTransport错误/截断JSON有限处理，不补成通过。 |
| T19 | PASS（mock HTTP），401/429/超时/重试预算和脱敏；供应商真实故障NOT_RUN。 |
| T20 | PASS（最小文字协议测试），schema/vision/tools实际能力保持untested。 |
| T21 | PASS（合成模型+真实Windows编译），前后节引用及实际aux编号核对；仅计划登记的后续标签局部记PENDING_FULL_REFERENCE_CHECK，原编译FAIL记录不改；全文必须解析。真实模型复杂长讲义NOT_RUN。 |
| T22 | PASS，依赖条件/计划hash变化使旧下游缓存键失效；真实模型多轮修改链NOT_RUN。 |
| T23 | PASS，人工预定错误级数fixture被阻塞，合法交错级数不误拦。 |
| T24 | PASS，量词/对数定义域疑点及约分丢定义域的fixture被送审/阻塞。 |
| T25 | PASS，符号未知为UNKNOWN/NEEDS_REVIEW。 |
| T26 | PASS，数值一致仅numeric_spotcheck_passed，不升级一般证明。 |
| T27 | PASS，中文/空格/括号路径实际导入/编译/交付；长路径故障已留证并缩短内部路径。 |
| T28 | PASS，三组同名讲义按dataset/path/hash区分，51原件hash再核对。 |
| T29 | PASS，自定义数学环境、嵌套和真实跨度；未知片段保留opaque。 |
| T30 | PASS，coth/setminus/leqslant/geqslant不误报。 |
| T31 | PASS（正确阻塞），实际破损tabularx编译FAIL并定位slides.vrb:9，数学单元及source_map完整、日志保留；未声称自动修复任意表格。 |
| T32 | PASS，短定义+明确关联举例同frame。 |
| T33 | PASS（合成及源转换），长证明完整语义边界/假设重复；所有复杂证明教学连贯性须教师审核。 |
| T34 | PASS，Windows实际一个逻辑frame/两overlay全部渲染。 |
| T35 | PASS（自动边界检查），完整句子/列表item安全拆分、题解pause及空布局页回归，六组源转换均无编译溢出；教师逐页教学连贯性NOT_RUN。 |
| T36 | NEEDS_REVIEW，不切公式/数组内部；任意等式链等价重排未通用实现，不能拆者阻塞。 |
| T37 | PASS（约束），不允许截图/缩放正文，无法安全排的完整单式阻塞；真实复杂长公式矩阵仍需审阅。 |
| T38 | PASS，四档静态规则及实际字体probe；自然数学下标不误判。 |
| T39 | PASS（渲染器/合成），仅六类block、题解标签，无内容空block；三章实际页面另行门禁。 |
| T40 | PASS（确定性渲染），完整一级三态目录；三章实际目录已进入完整草稿。 |
| T41 | NEEDS_REVIEW，长目录有分组，任意长标题容量仍需实际编译/复核，不使用过小字号。 |
| T42 | PASS，FDU缺资源明确不可用，不回退。 |
| T43 | PASS，两个不同主题hash拒绝任取；当前三份真实主题同hash。 |
| T44 | PASS，原sty不改、独立适配、实际四档probe；51原始hash无变化。 |
| T45 | PASS，独立从实际TeX检测遗漏/未授权新增，不能只信source_map。 |
| T46 | PASS，不等号篡改及新增数学篡改被识别；通用逻辑等价判断未声称实现。 |
| T47 | PASS，真正中间overlay越界的Windows fixture被阻塞，3物理页全渲染；初始错误fixture证据保留。 |
| T48 | PASS，旧PDF和实际失败编译不冒充新成功。 |
| T49 | PASS，Windows真实拒写PDF句柄打开期间新版本构建正常。 |
| T50 | PASS，默认无总结/谢谢页，渲染只含获批内容及目录。 |
| T51 | PASS，受控ZIP拒绝穿越、危险附件/符号链接并有大小/压缩比/成员限制；非所有压缩格式已支持。 |
| T52 | PASS（原生最低保护/实测openout）；完整文件/网络隔离NOT_RUN，isolated未实现。 |
| T53 | PASS，输入目录同名假编译器不被选择，使用绝对路径。 |
| T54 | PASS，源文本/模型字符串不构成审批、不会执行Python或HTML；不宣称所有提示注入语义都可判定。 |
| T55 | PASS，环境、异常、日志摘要和实际ZIP synthetic敏感值检查；聊天真实key未复制。 |
| T56 | PASS，Host/Origin/CSRF及artifact_id映射/hash；单本机用户，不宣称多租户权限。 |
| T57 | PASS，请求预算持久化且超限阻塞，有限修复；扩充预算需显式改环境并重启。 |
| T58 | PASS，取消后旧token和晚到结果不提交。 |
| T59 | PASS，实际工作流源ZIP在干净中文目录真实重编译并全页渲染。 |
| T60 | NEEDS_REVIEW（语义），范围/题解/习题/答案等有确定性产物检查；自定义教学比例/难度等必须审阅质量报告，不能仅凭计划字段声称落实。 |

三章真实讲义生成3格：BLOCKED（未启用新API密钥）。三章转Beamer6格：按 reference_matrix.md 逐项，不能用本表的合成回归PASS替代。人工视觉/数学审核：NOT_RUN。
