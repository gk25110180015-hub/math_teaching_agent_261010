# M0 工程审计

根目录：D:\\研究生阶段\\数学教学agent。已完整阅读 CODEX_MATH_TEACHING_AGENT_WINDOWS11.md（版本 1.0）。

初始目录包含规范及第一章、第二章、第三章、第四章资料，没有既有应用工程、Python 入口、数据库、配置或测试可复用，根目录也没有 .git。审计过程中出现的 math-teaching-agent 为本次创建的新工程；初始 .gitignore、pyproject.toml、src 与 reports 由本次实现建立，并非历史用户代码。

新工程路径为 D:\\研究生阶段\\数学教学agent\\math-teaching-agent。原始四章目录及规范保持原样。参考文件按数据集 ID + 相对路径 + SHA-256 建立索引，禁止用同名讲义 basename 覆盖。第一至三章详细完整性与依赖结果由 reference_audit.md、reference_index/manifest.json 提供。第四章只记录存在，不纳入本次三章验收矩阵。

复用映射：现有 Python 3.12.4 用于创建虚拟环境；现有 TeX Live 2024 绝对路径用于编译；用户 .sty 与图片从原资料建立快照后使用；没有旧业务模块需迁移。

后续按 M1–M5 实现持久化工作流、UI、供应商、可信本机编译、源文件交付与验收。无环境密钥，因此真实 API 验收当前 NOT_RUN；真实 Windows 编译条件已具备，尚待运行。
