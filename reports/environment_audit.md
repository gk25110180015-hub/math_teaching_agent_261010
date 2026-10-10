# M0 本机环境审计

执行时间：2026-09-19。只读检测，没有安装或修改全局依赖。后续项目虚拟环境以锁文件和阶段测试记录为准。

| 检查 | 状态 | 实测证据 |
|---|---|---|
| Windows | PASS | OS 10.0.26200.0；注册表 DisplayVersion=25H2、CurrentBuild=26200、UBR=9457。属于 Windows 11 build；ProductName 仍为历史字符串 Windows 10 Home China。 |
| Python 3.12 | PASS | D:\\anaconda\\python.exe --version → 3.12.4 |
| uv（审计初始） | NOT_INSTALLED | PATH 与基础 Python 分发均未发现；主工程将安装项目内工具。 |
| XeLaTeX 绝对路径 | PASS | D:\\texlive\\2024\\bin\\windows\\xelatex.exe --version → XeTeX 0.999996 / TeX Live 2024 |
| TeX 宏包 | PASS | kpsewhich 找到 ctexart、ctexbeamer、beamer、amsmath、amssymb、fontspec、tabularx、tikz。完整路径在 JSON。 |
| 字体文件 | PASS | kpsewhich 找到 FandolSong-Regular.otf、FandolHei-Regular.otf；Windows Fonts 下存在 SimSun、SimHei、Microsoft YaHei。仅文件存在检测，不代表视觉验收。 |
| D 盘可用空间 | PASS | 253826785280 bytes |
| 本地端口 | PASS | Python socket 成功绑定 127.0.0.1:8765 后关闭 |
| 环境 API 密钥 | NOT_RUN | MATH_AGENT_API_KEY 不存在，LIVE_API_ENABLED=false；未使用对话中暴露的密钥。 |
| Windows 实际编译 | NOT_RUN | 此阶段仅执行编译器版本检查；编译测试待 M2。 |
| 人工视觉验收 | NOT_RUN | 尚无本次产物。 |

初始 Python 已有 HTTPX 0.27.0、Pydantic 2.5.3、SQLAlchemy 2.0.30、SymPy 1.12、pytest 7.4.4、Jinja2 3.1.4；缺少 FastAPI、pydantic-settings、Alembic、pylatexenc、pypdfium2、pdfplumber、Playwright、python-multipart。项目必须使用独立虚拟环境，不改 Anaconda 全局版本。

分类说明：这里 PASS 只对应列出的检测命令，不表示 mock 业务、真实 API、实际 PDF 编译或人工视觉通过。
