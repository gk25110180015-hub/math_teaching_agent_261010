# M5：Windows 集成与交付

实际 Windows 11 build 26200 / Python3.12.4 / TeXLive2024。Setup用锁文件及项目缓存，Run/Stop只管理本项目进程身份；PS7与Windows PowerShell5.1检测/测试均留证据，未修改永久执行策略、防火墙或全局Python。

实测：启动→创建中文任务→停止→重启恢复同一任务；后台worker独立于网页；强制编译取消只终止所属进程树；租约重领拒绝旧结果；正在占用的PDF不阻塞新版本；ZIP在全新中文目录重新编译；环境密钥/私有文件不进入编译环境或源包。见 `ui_windows_validation.md`、`delivery_validation.md`、`compiler_math_validation.md`。

另实测终止本测试的真实 worker 子进程，在真实5秒租约过期后重新领取，已完成合成章节检查点仍在且 fencing token/attempt 递增；`worker_crash_recovery.log` 为1 passed。这是合成步骤的实际进程恢复，不冒称真实供应商崩溃调用已验证。

最终强化浏览器4用例验证了真实PDF/ZIP/全部PNG、明确增删、自定义和实际未定义TeX错误后的重试。早期仅测状态的过宽断言已经纠正，不作为业务成功证据。Windows长路径导致的原子临时文件失败已用短构建目录与短临时文件名修复，旧失败证据保留。

三章原始PDF共233物理页已实测渲染，仅作为基准。新的三章×双模板六组源转换另见 `reference_matrix.md/json`；三个专题的真实API讲义生成均 NOT_RUN，不能用mock示范顶替。

最终六组源转换共586物理页全部渲染，六组来源检查PASS，无编译溢出与几何blocking；几何接近正文边界、原稿公式下标及字体替换等仍列人工复核。编译仍因缺失书目为FAIL。

**M5完整验收尚未通过**：新API密钥/live启用、原始资料缺失书目、教师审核均按最终报告列出。部署仅本机可信模式；隔离沙箱未实现，隔离测试 NOT_RUN。所有缺条件或失败保留原始证据和恢复路径。新增failure_diagnostic.json通过受控artifact_id下载，编译详细日志和草稿保留本地版本目录。
