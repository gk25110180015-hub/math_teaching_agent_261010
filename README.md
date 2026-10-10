# 数学教学 Agent（Windows 11 本地版）

## 2026-10-10 完整运行快照

此仓库包含当日本地项目的源码、网页实例、输入、生成结果、历次产物、审批、模型请求计数、测试与验收记录，以及四章参考材料和完整教材原稿。主工作区保存 **15 个实例、1,569 条产物记录、1,652 条事件、55 个计划版本、57 条决策和 16 条人工复核记录**。其他历史测试工作区和数据库也一并保留。数据库快照时间和各表计数见 `snapshot/database-snapshot.json`，迁移验收见 `snapshot/verification.json`。

### 下载后恢复同一批实例

建议使用 Windows 11，将仓库克隆到较短的路径；本仓库包含大量历史文件。使用 Git 时先执行 `git -c core.longpaths=true clone https://github.com/gk25110180015-hub/math_teaching_agent_261010.git`。准备 Python 3.12 或 3.13（或可用的 uv）；生成/重新编译 PDF 还需 XeLaTeX，视频渲染需 Edge/Chrome。进入下载的仓库根目录执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\Run-Snapshot.ps1 -Setup -OpenBrowser
```

首次运行按 `uv.lock` 安装依赖；以后可省略 `-Setup`。默认网页为 `http://127.0.0.1:8765`；若原项目也在运行，添加 `-Port 8766`。脚本自动使用本仓库 `workspace` 中的历史数据库、`reference_data` 中的参考材料，并优先加载本地 `snapshot/model-environment.json`；没有该文件时读取仓库中的 `snapshot/model-environment.example.json`。

公开仓库包含模型名称、接口地址和配置模板，不包含有效 API 密钥。已有实例和生成结果无需模型密钥即可浏览、下载；继续调用真实模型时，将 `snapshot/model-environment.example.json` 复制为 `snapshot/model-environment.json`，填写 `MATH_AGENT_API_KEY` 和 `MATH_AGENT_DEEPSEEK_API_KEY`，再启动。此本地文件已由 Git 忽略。原机器的完整配置已保留在本地复制目录的同名文件内，启动过程不会打印密钥值。

页面中会列出原来的实例和结果；浏览器最后选中的实例属于本地浏览器状态，新机器需要自行点选。历史时间戳、审批和输入哈希保持原样；旧编译日志中的原机器路径作为历史证据保留，实际文件访问使用当前副本路径。主工作区在快照时没有排队或运行中的任务。

`Run-Snapshot.ps1` 会把来自旧目录的进程记录改名归档，再创建本目录的服务和 worker，不会操作旧记录中的进程。停止本副本使用 `scripts/Stop-Local.ps1`。原始 Python 虚拟环境、工具缓存和测试缓存已保存在本地复制目录，但不提交到 GitHub；下载者通过锁文件重建 Python 依赖。操作系统、字体、XeLaTeX、浏览器和外部模型服务仍依赖运行机器，不能保证未来重新生成的内容逐字相同。

以下保留原项目功能说明；其中原机器启动路径应替换为当前仓库目录，恢复本快照优先使用上面的 `Run-Snapshot.ps1`。

独立运行的 Python 应用：浏览器界面 + FastAPI + SQLite 持久任务 + 单独 worker。提供“专题生成讲义”和“讲义 TeX/ZIP 转 Beamer”，可下载 TeX、完整源码 ZIP、PDF、逐页预览及检查报告。运行不依赖 Codex 会话，不需要 Node、Docker、WSL 或 Redis。

**2026-09-28 新增数学概念可视化。** 首页侧栏或工作流菜单进入“数学概念 → 视频与交互页面”，也可打开 [本机可视化工作台](http://127.0.0.1:8765/visualizations)。模型先给出 3–4 个候选方案，选择后提出数学细节选择题；每轮选择和可选的自定义建议都会交给模型重新完善分镜。仍有歧义时继续提问，全部解决后核对并确认，才开始代码生成、检查和视频渲染。

2026-09-30：生成与修复按确认分镜逐项落实放大、左右符号颜色和关键状态停留，每镜采样五个时间点，并把实际绘图位置/颜色交给代码审阅。导数单点斜率与区间单调性须明确区分；数学状态允许布尔量和非空中文说明，无效数据会指出字段路径。对 v2 失败代码采用逐字匹配的局部替换，保留未涉及的计算和交互，拒绝模糊锚点、重叠替换和整段重写；每版仍重新执行全部检查。旧受阻任务重试时继续使用已确认方案及最后失败版本，重新应用当前检查契约。

讲义转 Beamer 的内容页标题由所选模型依据实际分页内容概括生成，通常 6–16 字、最多 32 字；章节名继续用于目录和章节导航。标题生成覆盖分页后的正文及已批准新增页，参与编译和版面检查；重新分页后只对内容改变的页重新拟题。目录页仍显示“目录”，原讲义数学正文继续做保真检查。

视频为 **960×540 WebM 无声动画，配中文字幕**；交互页面提供时间轴、播放暂停和数学参数滑杆。三维曲面通过 Canvas 投影绘制，可设计视角滑杆。视频与交互页共用模型生成的 JavaScript，交付 `video.webm`、可离线打开的 `interactive.html`、`scene.js`、计划/检查报告和 `source_bundle.zip`。真实 API 支持模型能够规划的数学概念；MOCK 仅提供导数及梯度下降的明确标记测试样例。

**2026-09-29 控件与修复流程更新。** 新生成的交互页区分分镜演示与自由探索：演示时按方案切换示例和动画步长；调参后按当前参数重算图像、公式、数值与中文字幕；重置可返回演示。若当前分镜锁定了参数，点击“自由探索”即可手动调节。控件显示实际值，不适用时显示禁用原因。制作前逐镜头测试控件的端点、中间值与动态状态，再结合浏览器证据审核数学内容。失败重试从最后代码及累计问题继续修复，保留原计划、用户选择、审批和累计请求数；不会复用旧版生成协议的缓存。记录见 [控件故障修复报告](reports/visualization-controls-20260929/RESULT.md)。

渲染复用本机 Edge/Chrome 和项目 Playwright，无需 Manim、系统 FFmpeg、Node 构建链或新增云服务。另一台机器运行 `Setup-Windows.ps1` 安装锁定依赖后，需有 Edge/Chrome，或执行 `.\.venv\Scripts\python.exe -m playwright install chromium`。也可用 `MATH_AGENT_BROWSER_PATH` 指定浏览器。程序不会执行模型 Python/系统命令：绘图代码在无网络的浏览器 Web Worker 中运行，网页预览使用独立 sandbox 源，渲染子进程不接收模型密钥。单帧超时、无效数值、静态画面、无效果滑杆和编码错误会阻止交付并进行有限修复，失败保留诊断与草稿。

页面刷新后可继续已保存的方案；提交建议会使原确认失效，必须核对新版本。已经开始制作的任务不能改写计划，需要新建任务。自定义建议入口覆盖候选选择、答题和最终核对阶段；本轮调试按要求只自动选择选项，不提交自定义建议。所有动画仍需教师核对数学与视觉效果，自动检查不代替教学验收。验收证据见 [可视化功能报告](reports/visualization-20260928/RESULT.md)。

命令行完整流程验收（使用独立测试目录；真实调用需先导入本机模型环境）：

```powershell
.\.venv\Scripts\python.exe scripts/verify_visualization_workflow.py
.\.venv\Scripts\python.exe scripts/verify_visualization_workflow.py --live --topic '导数'
```

**2026-09-27 已修复删除选择的计划展示、空章节和过度拆页，见[最新修复与对比](reports/plan-layout-20260927/RESULT.md)。** 最新第四章任务由 208 frame／208 物理页调整为 134 frame／178 物理页（含逐步显示）；保留原删除授权和审批，44/58 对题解或证明可同 frame。每组先实际尝试 normalsize、small、footnotesize，再对仍溢出的组拆页。1144 项隔离本地回归和最终版 7 项实际 Edge 工作流通过；202 个下载文件及源码 ZIP 干净编译通过。本轮模型 mock 测试与真实编译分别记录，真实模型 API 未调用，教师复核未完成。

**2026-09-26 已修复上传第四章 TeX 转 Beamer 的 QUALITY_BLOCKED 故障，见[该轮修复与验收记录](reports/quality-recovery-20260926/RESULT.md)。** 当时原任务恢复生成 209 页，原稿、审批和失败产物保留。该轮隔离本地回归 1134 项通过，6 项实际 Edge 工作流通过（模型 mock、实际 Windows 编译），原任务下载及源码 ZIP 干净重编译通过。真实 API 仅完成最小连通探针，教师数学/视觉复核未执行。

**此前三章真实制作与交付核验已完成，见[最终交付清单](reports/iteration4/DELIVERABLES.md)及[分层验收报告](reports/iteration4/FINAL_ACCEPTANCE.md)。** 当时1118项本地回归、14项实际Edge工作流通过，模型部分使用mock。真实API三章最终为11/18/23页、累计70/152/191次请求；已完成源码ZIP在Windows干净目录重编译、当前/历史下载核验、全文及全部52页agent审读。第一章补齐绝对值应用；第二章补齐极限比较与答案导航；第三章补齐夹逼练习、抵消反例、经济单位和证明前提。三章均为待教师审核，**教师数学/视觉验收NOT_RUN，M5整体仍为PARTIAL / NEEDS_REVIEW**。

原稿固定基准分别为16项覆盖、14项覆盖/2项部分覆盖、19项覆盖/3项部分覆盖；第一章的逐节目标提示及价格模型单位仍有通用教学改进项。53份清单内原件哈希保持不变。三章双模板课件共522页，六个源码ZIP均有实际干净编译证据（历史2组、本轮补4组），文件在同一交付清单中。第二、三章预算为480请求/每单元12/全局12；第一章请求上限已从60正式增至240，局部2/全局2保持。API失败与恢复、历史产物均保留，详见[实施记录](reports/iteration4/IMPLEMENTATION_AND_TESTS.md)。

模型环境已配置时，新建页面默认“真实 API / gpt6”，可选择 deepseek-flash 或 deepseek-v4-pro；未配置时默认明确标识的离线合成 MockProvider。三模型配置、临时故障切换和本轮测试结果见[第三轮验收报告](reports/iteration3/FINAL_ACCEPTANCE.md)。MOCK演示数列极限流程，不能当作任意专题的真实教学生成。[第一轮验收报告](reports/FINAL_ACCEPTANCE.md) 保留原有结果和失败条件，不代表最新配置状态。教师逐页视觉审核不会由程序代替。

## 启动

在 PowerShell 中进入本工程目录（注意原始三章材料在上一级，保持不变）：

```powershell
Set-Location -LiteralPath 'D:\研究生阶段\数学教学agent\math-teaching-agent'
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\Run-ExtendedReview.ps1 -OpenBrowser
```

浏览器入口为 **http://127.0.0.1:8765**。推荐入口采用本轮长篇实测使用的 30/600/600 秒连接、读取及单次总等待；`Run-Local.ps1` 仍可使用较短的默认配置。启动脚本以隐藏窗口运行服务与 worker，保存各自 PID/身份和日志；关闭网页不取消任务。不修改系统执行策略、防火墙或全局 Python。如果组织策略禁止运行脚本，可使用下列两终端命令，无需放宽全局策略：

```powershell
# 终端一
.\.venv\Scripts\python.exe -m math_agent.cli serve --host 127.0.0.1 --port 8765
# 终端二
.\.venv\Scripts\python.exe -m math_agent.cli worker --concurrency 1
```

手动 CLI 读取当前终端环境。若要使用已配置的 Windows User 变量，先在每个终端执行下方“导入环境并检查”代码；MOCK 任务不需要密钥。启动脚本会自动补入当前进程尚未设置的 API、模型和流式开关 User 变量，已有进程环境值优先。

停止脚本管理的进程：

```powershell
.\scripts\Stop-Local.ps1
```

脚本只终止本项目记录且身份匹配的进程树。手动启动的两个终端用 Ctrl+C。重新启动会保留任务、审批和章节检查点；过期 worker 租约会重新领取，中断的步骤会恢复。外部 API 若在响应边界崩溃，重试可能重复计费，不能承诺供应商调用恰好一次。

需要单独查看基准任务时，可指定独立工作区和端口；默认工作区与 8765 入口保持原样：

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\Run-ExtendedReview.ps1 -Workspace 'workspace\iteration2-live' -Port 8766 -OpenBrowser
.\scripts\Stop-Local.ps1 -Workspace 'workspace\iteration2-live'
```

`-Workspace` 接受相对工程根目录的路径或绝对路径，只允许工程 `workspace` 本身及其子目录，不允许路径跳出或链接重定向。该实例的数据库、日志与进程记录位于所选目录；停止时必须使用相同工作区，并继续核对项目、工作区、PID、可执行文件和启动时间。启动脚本仅为子进程设置所选 `MATH_AGENT_WORKSPACE`，随后恢复调用终端原值。不要同时为同一工作区启动重复 worker。

## 第一次安装与环境检查

当前机器的 `.venv` 已实际安装并用 `uv.lock` 锁定；本机已检测到 Python 3.12.4 / TeX Live 2024。另一台 Windows 机器需要 Python 3.12 或 3.13 和 XeLaTeX；请安装官方 [Python](https://www.python.org/downloads/windows/)、[TeX Live](https://tug.org/texlive/windows.html)，无需管理员权限运行本应用。

```powershell
.\scripts\Setup-Windows.ps1
.\scripts\Doctor-Windows.ps1
# 等价 CLI
.\.venv\Scripts\python.exe -m math_agent.cli doctor
.\.venv\Scripts\python.exe -m math_agent.cli references index --root '..'
```

Setup 优先项目内 `.tools\bin\uv.exe`，使用项目缓存/虚拟环境；不改全局 Python/PATH。`uv sync --locked --extra dev` 是依赖契约，实际安装版本在 `uv.lock`。Doctor 的“编译器存在”仅说明版本命令成功，不能代替 PDF 编译或数学验收。

## 配置真实 API（只在本机环境中输入）

本机已按用户授权保留原有 gpt6 配置，并新增 DeepSeek 环境变量；已有配置无需再次输入。界面提供 `gpt6`、`deepseek-flash`、`deepseek-v4-pro` 三个选项，不选择时使用 `gpt6`。`gpt6` 是显示名称，实际请求中的模型名仍为 `gpt-6-astra`。首次配置或更换密钥时，在本地终端运行以下命令，按隐藏提示输入：

```powershell
.\.venv\Scripts\python.exe .\scripts\Configure-LiveApi.py --provider gpt6 --streaming
# 新增或更新两个 DeepSeek 模型共用的密钥；不会改动 gpt6 的任何 User 变量
.\.venv\Scripts\python.exe .\scripts\Configure-LiveApi.py --provider deepseek
```

该脚本只把密钥保存为 Windows 当前用户的 `MATH_AGENT_API_KEY` 环境变量，同时设置 `MATH_AGENT_LIVE_API_ENABLED=true`、`MATH_AGENT_API_BASE_URL=https://oneapi.advancedsolver.com/v1`、`MATH_AGENT_MODEL=gpt-6-astra`。本接口已通过 [SSE 文本流探针](reports/iteration2/streaming_probe.json)，推荐附加 `--streaming`，它设置 `MATH_AGENT_LLM_STREAMING=true`；本机已启用此 User 变量。其它安装默认仍关闭流式，省略该参数会将流式变量设为 false。长非流式请求曾遇到网关约 60 秒超时，流探针成功尚不能代替完整长讲义验收。

配置报告仅记录是否已配置，不记录密钥值；最早的 [环境配置报告](reports/iteration2/environment_configuration.json) 先于流式探针，按其时间读取。程序**不会读取 `.env` 文件**；`.env.example` 只是变量说明。浏览器没有密钥输入框，密钥不写入源码、命令参数或工程配置文件。

DeepSeek 脚本仅写入 `MATH_AGENT_DEEPSEEK_API_KEY` 和 `MATH_AGENT_DEEPSEEK_API_BASE_URL=https://api.deepseek.com`，不覆盖旧接口、旧密钥、模型名或全局 live 开关。两个 DeepSeek profile 发送 `thinking={"type":"enabled"}`、`reasoning_effort="high"`、`stream=false`；只读取最终 `content`，不归档、展示或回传 `reasoning_content`。参数依据 [DeepSeek 思考模式文档](https://api-docs.deepseek.com/guides/thinking_mode/) 与 [Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/)。每次配置产生独立 `reports/iteration3/environment-*.json`，旧报告保持不变。

导入环境并检查（已有终端不会自动更新环境；以下代码不输出值，当前进程已设置的值优先）：

```powershell
. .\scripts\Common-Windows.ps1
Import-AgentUserEnvironment
# 单模型能力验证，失败不借用其它模型的成功结果
.\.venv\Scripts\python.exe -m math_agent.cli provider check --live --model gpt6 --no-fallback
.\.venv\Scripts\python.exe -m math_agent.cli provider check --live --model deepseek-flash --no-fallback
.\.venv\Scripts\python.exe -m math_agent.cli provider check --live --model deepseek-v4-pro --no-fallback
.\scripts\Stop-Local.ps1
.\scripts\Run-Local.ps1 -OpenBrowser
```

已有服务须停止后重新启动，才能继承配置；手动启动的服务用对应终端 Ctrl+C 停止。在任务输入页选择“真实 API”。缺少变量时任务会明确 BLOCKED，不静默换成 mock。连通测试发送最小文本请求，不探测 `/models`、视觉或工具调用；价格未知记 null。连通成功只证明这次文本请求成功，不能替代完整教学工作流验收。配置与首个检查证据见 [环境配置记录](reports/iteration2/environment_configuration.json) 和 [连通检查](reports/iteration2/provider_initial_check.log)。

常规任务将用户选定模型作为首选；首选遇到 HTTP 504 等临时服务错误后，按 `gpt6 → deepseek-flash → deepseek-v4-pro` 的优先顺序尝试剩余已配置模型。切换只是本次调用的恢复策略，不改写用户选项或已确认的任务内容；后续独立调用再次从首选开始。每次实际请求仍计入原任务预算，切换不能绕过请求、修复或全文审核上限；全部候选及有限重试耗尽后仍会保留日志和检查点并报告阻塞。未配置密钥、数学审阅否决、JSON 校验失败和预算耗尽不能假装成另一个模型已经成功。

HTTP 200 也可能没有交付正文。本轮已针对实际出现的空流式响应增加恢复：空正文、异常 SSE 传输协议可临时切换备用模型，并保留调用元数据和接收字节哈希。完整的数学否决、业务结构错误、明确拒绝和长度截断仍按各自规则处理。

长篇审阅可使用 `.\scripts\Run-ExtendedReview.ps1` 启动同一应用：每个模型尝试的连接等待为 30 秒、读取等待与总期限均为 600 秒，仍按原顺序切换模型。可传入原有 `-Workspace`、`-Port`、`-OpenBrowser` 参数；启动前先停稳该工作区。此脚本只给启动的进程设置非密钥超时变量，不改变 Windows 用户密钥或任务预算。例如，保留的章节任务使用 `-Workspace 'workspace\iteration2-live' -Port 8766`。较长等待不能解除供应商自己的 HTTP 504 网关期限。

需要一次验证三个模型时，可运行 `.\.venv\Scripts\python.exe .\scripts\verify_model_capabilities.py --execute-live`。它严格按 gpt6、flash、pro 顺序执行，每个模型关闭 fallback、网络重试和结构修复，最多 3 次 HTTP 请求；每次结果及失败分别归档到 `reports/iteration3/`，成功能力按实际模型写入 `reports/model-capabilities/<model_id>.json`。不加 `--execute-live` 只记录 NOT_RUN。CLI 不加 `--no-fallback` 时可测试实际恢复行为，报告会区分请求首选与最终成功模型，不把 DeepSeek 的成功标成 gpt6 可用。

启用 live 后，当前教学文字和少量相关风格片段会发送到该第三方网关。尚未验证其数据保留政策、模型身份、上下文上限或图片能力。当前页面图片不发送模型，采用本地人工复核。

## 两条流程

1. 讲义：输入专题、难度 → 明确确认本次资料/模板可信 → 提出计划 → 选择证明、例题、习题及答案策略（每题末项自定义，可修改大纲标题）→ 核对差异并确认 → 执行逐节生成与检查 → 全文编译/渲染 → 逐页及质量报告人工复核 → 下载。
2. Beamer：上传 `.tex` 或带依赖的 `.zip` → 选择默认/FDU模板 → 核对源单元、大纲、精确删除及新增内容 → 确认 → 来源核验与排版候选编译 → 所有物理页及 overlay 检查 → 人工复核 → 下载。

单个 TeX 缺图像等依赖时，上传完整 ZIP。ZIP 有多个主文件时，在界面“ZIP中的主文件”中填写入口相对路径（API 对应 `main_file`），或只保留一个主 TeX 入口。原始上传保存成不可变快照。已锁定输入需要改变时，新建任务并重新审批；“重试”只恢复原输入/计划，不能绕过内容变化的重新确认。

勾选删除后，点击“保存选择并更新计划”，再核对保留章节和删除摘要。删除题目／定理时关联解答／证明会同时列入效果；取消原勾选并保存即可恢复。无保留内容且无获准新增内容的节不生成目录项。已确认的旧计划继续保留原始签名，界面按其删除授权显示实际保留范围。

Beamer 输入页提供“从本地完整原稿补齐已引用的真实书目”，**默认不勾选**；只有找到参考目录下的 `大学数学（一）(1).tex` 才可用。明确勾选后，仅将本次正文实际引用且缺失的条目从全稿原文复制到独立派生副本。原始上传字节、原快照和全稿均保留；已有条目不被覆盖，冲突或未知引用仍须处理。计划在确认前展示条目原文、出处行号和哈希，来源补充纳入计划 hash 与本次确认范围。刷新和交付 `plan.json` 保留同一来源记录。完整来源审计见 [source_audit.md](reports/iteration2/source_audit.md)，实际界面与编译验证见 [ui_validation.md](reports/iteration2/ui_validation.md)。

新增内容指定实际 section；删除例题时会把明确关联的解答列入确认清单。模板切换、范围/顺序变化是内容变更。自动合法字号调整与安全语义拆页不让用户重新确认同一个计划。四档字号仅为 `footnotesize/small/normalsize/large`，不会用缩放、删除证明或缩小到 scriptsize 解决溢出。

某些无法可靠展开的原始 TeX 会作为 `opaque_tex` 保留；并不代表已理解其全部语义。缺书目、未知宏、不可安全拆分的公式/长列表均可能阻塞。程序保留草稿，不以编译成功代替数学正确，也不把渲染成功当成人工视觉通过。界面上的具体质量问题、来源对照和每页 hash 才是审核对象。

## 恢复、日志和交付

- 默认数据库：`workspace/agent.db`；编号 SQL 迁移：`src/math_agent/migrations/`。SQLite WAL，短事务领取、心跳与 fencing token 防止旧 worker 覆盖新结果。
- 输入快照：`workspace/inputs/<run_id>/`；运行索引与失败记录：`workspace/runs/<run_id>/`；分节草稿/PDF 构建使用短路径 `workspace/b/`，具体位置见运行索引 `latest_build.json` 和数据库 artifact_id 映射。
- 启动日志：`workspace/logs/`；进程记录：`workspace/runtime/`；测试证据：`reports/` 和 `workspace/` 下独立验收目录。
- 失败任务保留原审批、成功章节和日志，点击“重试”从失败节点继续。原文缺失/语义变更须新建任务补齐资料。取消后晚到的模型响应不会提交。
- 结果页“文件与检查证据”顶部提供“下载讲义 TeX”（Beamer 为“下载课件 TeX”）、“下载 PDF”和“下载完整源码 ZIP”。下方仍可下载 `plan.json`、`quality_report.json`、`decision_coverage.json` 和各类来源/布局报告。单独主 TeX 可能依赖图片/主题，重编译时请下载完整源包；顶部按钮对应当前版本，旧版本保留在“历史交付”。
- 源包不含密钥、数据库或系统字体；私人 FDU 主题/图片的公开再分发许可未核实，仅用于本机交付。
- 新版本使用新目录，避免覆盖被 PDF 预览器占用的旧文件。失败编译不能返回历史 PDF 冒充成功。

讲义 TeX 转 Beamer 会保留练习环境、题号和答案跳转，并将原章节标签绑定到章节编号，避免引用误用幻灯片页号。兼容更新前保存的练习解析结果，无须重新上传或重做已确认计划。编译恢复后，自动排版仍按实际测量逐步调整字号与语义分页，正文保真检查继续执行。

任务页显示已用请求数、请求上限、每单元修复上限和全文修复轮数。生成计划后、首次点击执行之前，可在“请求与修复预算”中调高或调低三项上限并点击“保存预算”；确认计划后仍可调整，无须重新确认计划。请求上限最高 1000，至少比已用次数多 1；两项修复上限均为 0–20，0 表示禁用相应自动修复。保存后刷新仍保留，**不会自动执行**；有未保存修改时，执行按钮会提示先保存。

以上设置同时适用于讲义生成和课件制作。任务因编译或其他检查阻塞时，三项预算增额输入框默认展开；首次构建已开始的任务只能提高上限，累计用量不会重置。

初始修复预算分别为每单元 2 次、全文 2 轮；请求初值按首次执行配置持久化（本轮真实基准每任务 60 次），后续服务默认值不能覆盖。首次提交构建后不能再降低预算。预算耗尽进入 `BLOCKED`，普通“重试”不提高上限或清零次数。任务阻塞后，用户可在预算区明确填写更高上限及说明；保存保留原审批、累计次数、失败日志及产物，须另点重试。基准驱动自己的剩余总额上限仍独立约束请求，用户任务扩额不能绕过它。历史任务缺少预算基线时显示未知：先按保留证据核验导入，或由用户明确确认新的请求上限；仅修改修复预算不能悄悄采用当前请求默认值。

阻塞任务中的“已保存章节”提供逐项哈希验证的部分 TeX、检查点和已有 PDF。它们标记 `PARTIAL`，可能只覆盖部分章节或累计至某节，不能代替最终交付或教师验收。界面展示保存时间、检查点哈希及计划关联：旧记录没有计划身份时保持 `UNKNOWN`，不会猜测为当前计划；文件来源、所属任务或哈希不符会停止下载。预算与草稿交付验证见 [budget_validation.md](reports/iteration2/budget_validation.md)。

第四轮已按用户授权将原 CH02、CH03 任务先提高到 240/6/6，再提高到 480 次请求、每单元 12 次修复、全文 12 轮修复；原请求及接受/拒绝提案次数全部保留。增额也用于已耗尽的拒稿和全文修复恢复，不只改变界面数字。达到新上限后仍可在界面继续显式增额。

受阻讲义已有可核验的局部正文时，任务页提供“定点修复建议”：选择当前失败节的实际单元，填写具体建议后提交。建议绑定当前计划和正文版本，通过原任务的限定单元补丁、数学复核及编译继续执行；它不替代课程范围批准或教师判断。旧疑点与修复前状态保留，未改变正文的提案不能用来反复抽取审阅结果。草稿在轮询及提交失败时保留，旧页面或正文改变时会拒绝过期建议。只有存在完整恢复依据的受阻讲义显示此入口。

2026-10-07：修复“数学疑点裁定无效”提前中止正常局部修复的问题。普通审阅或工具检查已独立定位正文错误时，原任务可按已有预算修复这些单元，再对改变后的正文完整复核；原疑点及无效裁定继续保留。无效裁定不能授权修改其他单元，没有独立定位问题时仍会停止。此自动恢复分支要求实际修正正文，或修正工具已独立定位的现存核算表达式并重新获得符号核验 PASS；后者不得修改期望结果、假设、单元归属或无关核算。仅改备注、空白、注释或新增无关核算不能借此重抽裁定。需要补充实际核算证据时，仍可使用绑定当前候选的“定点修复建议”，由程序执行新增核算并完整复查；反复点击普通重试不会把原失败变成通过。同时修复从已接受的修订稿恢复时误改内部版本、导致刚提交的定点修复建议被判定为冲突的问题；计划、上下文或候选实际变化时仍需重新绑定。相关回归共 340 项通过（包含 Windows 实际编译），包含最小二乘法原失败记录、修复边界及 HTTP 提交到任务恢复的完整测试。

核算表达式修正后，普通审阅同时收到当前请求及经过 SHA 校验、实际重算的旧失败请求，疑点裁定也绑定同一份稳定证据。核算历史还注册为可逐字引用、带 SHA 的独立来源，供审阅区分旧输入失败和当前输入结果。若旧补丁新增的疑点把内部历史核算误称为来源不明，还会校验固定补丁并精确重放前后稿，提供该声明生成时的实际审阅问题；不猜测外部材料，不自动改动裁定。裁定仍须引用实际当前正文，不能只凭核算历史放行。旧普通审阅问题只有在新增事实支持的完整复审中才能重新裁定，原记录保留，同一证据重试不会反复抽取结论。

完整来源已提供但审阅仍坚持同一来源矛盾时，可对已绑定原声明和核算编号的问题做一次独立来源核实。撤回必须逐字引用当前正文、完整旧请求、原声明及原补丁和父审阅的 SHA 链；其他数学问题与警告保留。原裁定和新核实结果均不可覆盖，成功、保留或无效结论在重试时复用；仅明确未收到响应的传输失败可继续同一固定请求。新核实结果作为候选的固定证据依赖，不能通过删除记录重新抽取。

未定位的原疑点允许引用实际当前正文消解。若模型已明确判定该疑点得到解决、无未核实依赖或修复指令，却多填了所引用单元的归属编号，程序可将这一元数据恢复为原声明的 null；所有引用必须来自该实际单元，随后仍执行原来的完整校验。原响应、INVALID 状态和失败记录不改写，恢复映射及审计记录另行保存，不新增模型请求。此处理不适用于未解决疑点、推测新修复目标或无效证据；其他独立问题继续阻止交付。

讲义任务等待人工复核时，可填写“本轮希望改进的内容”并点击“重新运行自动检查”。意见会由全章审阅结合实际正文和已批准目标独立核实，再通过原局部修复流程处理；不扩大原审批范围，也不直接采纳错误建议。反馈草稿在轮询或提交失败时保留，成功提交后清空。其他工作流暂不支持意见文本，但仍可留空执行常规复检。复检会保留原计划审批和累计次数，将旧产物放到“历史交付”继续下载，生成新的检查结果；旧人工复核不能作为新产物的签字。章节缓存绑定检查代码、提示词、schema、依赖及编译配置，规则或前文变化时从经哈希验证的最新合法稿重新检查，不直接沿用旧 PASS。无检查点的已接受稿、连续中断和历史多版本也保留恢复证据。同一计划的全局修复契约发生不兼容变化时会明确阻断，需恢复原契约或显式迁移，不能借升级静默清零。

建议将独立意见按 `1. 2. 3.` 分行编号。结果页逐项显示“已满足、需改进、有依据拒绝、超出范围或未决”，并提供对应正文、批准目标依据和实际修改目标。需要改善教学解释或训练时，可以改进而不必先把正确数学判成错误；修改后重新核查。尚未核查、无效响应和旧正文回执不会显示成当前意见全部完成。没有明确编号时保留整段核查，不承诺自动拆分任意自然语言。

对审阅中明确指称目标、但长引文唯一命中其他实际单元的疑点，先保存原审阅并作一次定点核实：校验目标和来源逐字证据，保留真实依赖错误；不能仅因引用来自别处就删除意见。无法确认时阻塞正文修改，已完成裁定不能靠普通重试反复重抽；纯传输失败则保留原核实输入，重试从该处继续。所有原始审阅、裁定和失败均保留。此检查只处理可定位的引文风险，不是数学形式化证明。

讲义新增全章教学目标审阅，检查一般结论是否被特例替代、索引/初值是否有定义及引用是否适合学生阅读。能从真实编译日志精确定位到当前单元的排版溢出会进入原局部修复流程，修订后再次做数学检查与编译；不通过缩小字号或提高溢出容差放行。各次失败源码、日志和 PDF 分目录保留。自动审阅及无溢出编译均不代替教师数学和视觉验收。

## 分层测试

```powershell
.\scripts\Test-Windows.ps1 -Suite mock
.\scripts\Test-Windows.ps1 -Suite compile
.\scripts\Test-Windows.ps1 -Suite browser
.\scripts\Test-Windows.ps1 -Suite security
# 仅在启用环境密钥后
.\scripts\Test-Windows.ps1 -Suite live
```

浏览器测试优先使用已安装 Edge/Chrome，不要求安装 Node。所有非 live 的 Windows 测试命令临时清空 gpt6 和 DeepSeek 子进程密钥、关闭 live，并在结束时恢复调用进程的原环境；浏览器回归使用 MOCK 与真实本机编译，其中“API 未配置”截图只描述该隔离测试环境。真实 API 条件不满足时用例 SKIPPED；`-Suite live` 会从 Windows User 导入配置并发送实际请求，应单独执行。每次测试保存日志/JUnit，并使用新的临时目录，保留失败产物。

第二轮 [三章双模板比较](reports/iteration2/beamer_comparison.md) 分开列出原参考、第一轮草稿和新编译产物；[真实讲义基准说明](reports/iteration2/benchmark_driver_validation.md) 及 [运行记录](reports/iteration2/live-lectures/summary.json) 记录真实请求和恢复状态。两节smoke与正式CH01完成自动流程，其余两章保留阻塞；教师审核均未执行。第二轮当时的完整本地快照为546项通过（其中20项Windows编译相关节点），1项真实API测试排除、6项E2E未收集；独立6个mock浏览器用例是较早快照。随后仅修改产品CSS，四案例真实产物只读Edge验证61个文件下载及哈希通过；未调用模型或提交教师审核。provider转义77项及数值证据分类55项定向回归与完整测试重叠，审阅v3/v4真实正负对照另列，不混算或外推课程准确率。[具体改进对照](reports/iteration2/IMPROVEMENT_COMPARISON.md)记录模型/工具不足及尚未解决的教学覆盖问题。本轮没有微调模型权重。[第一轮矩阵](reports/reference_matrix.md)、[Windows/UI 验收](reports/ui_windows_validation.md)、[编译与数学核算](reports/compiler_math_validation.md) 和 [文件交付验收](reports/delivery_validation.md) 保留为基线。第二轮分层结果见 [第二轮验收报告](reports/iteration2/FINAL_ACCEPTANCE.md)；当前继续测试状态见 [第四轮记录](reports/iteration4/IMPLEMENTATION_AND_TESTS.md)。

## 安全与扩展边界

只绑定 `127.0.0.1`，检查 Host/Origin/CSRF，文件按 artifact_id 访问；浏览器用 textContent 展示用户/模型数据。TeX、PDF解析和SymPy核算子进程使用白名单环境，无 API 密钥。SymPy仅接受有界 JSON AST，不执行模型 Python。

**trusted_local 是原生可信本机模式，不是文件系统/网络沙箱。** 每个任务需要明确的输入信任确认；`isolated` 尚未实现，选择它会阻塞。不能把服务绑定公网或当成不可信文件处理平台。服务器迁移边界见 `reports/server_migration.md`。

技术实现核对了 [HTTPX 超时](https://www.python-httpx.org/advanced/timeouts/)、[Pydantic 模型校验](https://docs.pydantic.dev/latest/concepts/models/) 与 [uv 项目管理](https://docs.astral.sh/uv/guides/projects/)；以本项目锁文件和实际运行证据为准。
