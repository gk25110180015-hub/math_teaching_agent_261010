# Store 初始化修复后：完整五例浏览器整合复测

2026-09-20 03:14（Asia/Shanghai）执行，**5 passed in 54.34s；0 failed、0 errors、0 skipped**。使用现有 `tests/e2e/test_browser_workflows.py` 原样执行，未调整产品或测试断言。

这是实际 Edge、独立 FastAPI/worker、SQLite 和 Windows XeLaTeX 的浏览器流程验证。模型 provider 全部为 **mock**：父测试进程显式清空 API key、关闭 live 与 streaming；测试 fixture 还移除继承的全部 `MATH_AGENT_*` 后重新设置隔离环境。没有调用真实模型、没有导入 Windows User 配置，没有启动/停止 8765 或 8766，没有修改 benchmark 工作区。

| 用例 | 本轮结果 |
| --- | --- |
| 讲义生成、决策/标题编辑、确认执行、刷新恢复 | PASS；必须达到 `AWAITING_USER_REVIEW`，实际下载 PDF/源码 ZIP/全部 PNG |
| Beamer 精确删除及用户新增、FDU 适配摘要 | PASS；实际编译及源码/fidelity 断言 |
| 自定义计划输入与刷新保留 | PASS |
| 真正未定义 TeX 命令引起编译失败和重试 | PASS；断言 `UNDEFINED_CONTROL_SEQUENCE` 与 `QUALITY_BLOCKED`，不把任意异常当通过 |
| 完整原稿书目显式补齐、出处与原件保护 | PASS；实际编译、交付及来源哈希断言 |

执行命令（环境隔离值见 [invocation.json](invocation.json)）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/e2e/test_browser_workflows.py -m e2e --basetemp workspace/t/e5be2009 --junitxml reports/iteration2/ui-postfix-20260920-031401-721/pytest.xml -q -ra
```

- [完整日志](pytest.log)、[JUnit XML](pytest.xml)。
- [前快照](source-hashes-before.json)、[后快照](source-hashes-after.json)、[比较结果](source-hash-comparison.json)：`src/` 与 `tests/` 共 85 个实际文件的 SHA256 全部相同；只排除 `__pycache__` / `.pyc`。
- [浏览器上下文](20260920-031402/context.json)：实际端口 **64823**，独立工作区 `workspace/t/e5be2009/r0/w`。
- [截图、trace、控制台及服务日志目录](20260920-031402/)：7 张 PNG 截图、5 份 trace；5 份 console JSON 均无 page error。
- [退出核验](post-run-checks.json)：测试自清理自己的服务/worker 后，64823 监听数为 0。独立工作区及失败用例产物保留。

此轮是新增 Store 并发初始化修复后的单次整合复测，不重复宣称章节真实模型质量已通过。`live-unconfigured.png` 反映本轮隔离 mock 环境，不表示用户的实际 Windows User 配置缺失。

**真实 API 测试：NOT_RUN。教师数学/逐页视觉验收：NOT_RUN。** 已准备的真实产物只读 UI 脚本仍未执行，等待 root 在章节 driver 完成后启动相应服务并通知。
