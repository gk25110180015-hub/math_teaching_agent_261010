# 数学概念可视化功能验收

日期：2026-09-28。新增工作流 `visualization.create`，与原讲义、Beamer 共用模型配置、SQLite、独立 worker、请求预算、审批版本、任务取消及重试机制。

## 使用入口

[本机网页](http://127.0.0.1:8765/visualizations)。首页侧栏及新建任务的工作流菜单均有入口；最近任务中的可视化记录会跳转到专用页面。现有工作区和历史产物保留。

流程：输入概念/教学对象 → 模型生成 3–4 个候选 → 选择候选 → 模型提出数学歧义选择题 → 用户选择后模型更新完整分镜，必要时继续提问 → 核对并确认 → 生成动画代码 → 代码数学审核和有限修复 → 实际视频编码及交互测试 → 下载。

自定义建议在选候选、答题和最终核对时均可提交；有未提交建议时会阻止直接确认，避免丢失输入。本轮按用户要求跳过建议提交测试，保留入口与处理环节。首轮必须有澄清问题，未完成的问题和待应用决定会阻止确认。修订计划使旧确认失效；重复/过期提交返回冲突。

## 实现及交付

- `src/math_agent/visualization/`：独立契约、协作规划、确定性流程、离线测试样例、动画导出和浏览器渲染器。
- `src/math_agent/prompts/visualization_*.md`：候选、方案完善、代码生成、代码数学审阅四个模型角色。
- `src/math_agent/web/static/visualizations.*`：专用网页，复用原样式与 API 会话。
- 原有模块只增加工作流注册、输入类型、worker 分发、网页入口及可视化专用路由/防误用检查；没有改写原讲义或 Beamer 生成算法。
- Playwright 纳入运行依赖，`uv.lock` 同步；已用本机缓存执行 `uv sync --locked --extra dev --offline` 成功。

视频为 960×540 WebM（VP8/VP9）无声动画，含中文字幕。交互采用 Canvas 2D 和三维投影；模型生成的 `draw(ctx,t,p)` 同时用于视频与 HTML。页面提供参数滑杆、时间轴、播放/暂停、复位。暂不提供配音、MP4 转码、任意表达式输入器或画布直接拖点。

产物：`video.webm`、`interactive.html`、`scene.js`、`project.json`、`plan.json`、`quality_report.json`、起始/中间/结束截图、`source_bundle.zip`。HTML 可离线打开。MOCK 仅支持导数和梯度下降测试样例，其他概念使用真实 API。

模型代码仅在浏览器 Web Worker 内执行；后端不执行模型 Python 或 shell。渲染进程环境不含 API 密钥，浏览器禁用外部网络和 service worker。预览响应与 iframe 均采用不含 `allow-same-origin` 的 sandbox，生成代码无法读取工作台会话。所有下载校验文件 SHA-256，失败代码与诊断以草稿身份保留。

每个动画采样 5 个时间位置，并测试各参数的两端；检查数值、绘图区实际变化、视频头、解码尺寸和实际帧数。自动成功不等于教师数学或视觉验收，交付明确标为待教师复核。

## 已完成验证

- 新增单元/接口/持久化测试：16 项通过。包括多轮新增歧义、未确认禁止执行、取消后模型响应不得提交、渲染失败不得交付视频等。见 `unit-final.xml`。
- 实际 Edge 浏览器：9 项通过，其中新功能 2 项，原讲义/Beamer 工作流 7 项。见 `browser-regression.xml`，截图和 trace 在 `browser/20260928-220040/`。验证视频实际播放、唯一源 iframe、滑杆效果、刷新恢复、下载 ZIP、返回工作台；样例数值检验了差商公式和梯度迭代。
- 首轮全量本地回归：1157 passed、0 failed；运行中调整了新功能文件，因此该轮明确标记 `source_stable=false`，不能作为最终固定版本证据。保留 `../iteration4/local-full-20260928-215304-18b0a5fb.*`。
- 两个 MOCK 示例均实际生成视频和交互页面，见 `mock-/b9106d06/result.json`。
- 本机默认服务已重新加载，`/api/health`、`/visualizations`、页面脚本均返回 200。重启前确认默认工作区无活动队列。

- 第二轮固定版本回归：1160 passed、0 failed；见 `../iteration4/local-full-20260928-220823-e2b4c97c.*`。
- **最终完整本地回归：1161 passed、0 failed、0 skipped、1 deselected（真实 API 标记），source_stable=true，前后源文件哈希一致。** 运行263秒，见 [结果](../iteration4/local-full-20260928-222707-0e4f863f.md)、[JUnit](../iteration4/local-full-20260928-222707-0e4f863f.xml)、[完整节点及哈希](../iteration4/local-full-20260928-222707-0e4f863f.json)。包含原有1144项与新增17项，覆盖最后的周期视角/逐镜头采样改进、输入框属性及验收脚本修复。

两个真实模型示例均已产出视频和交互页面，结果如下；教师数学/视觉验收未执行。

### 真实导数示例

`live-/475c41bc/39a2929f5490489f9d484458beb98dd1.json`：已完成，实际累计 15 次请求（含模型切换和两轮代码修复）。生成 34 秒、960×540、VP9 WebM，567 个实际绘制帧、3,122,792 字节，视频已解码校验；h、函数预设、显示模式三个交互均验证有实际画面变化。末帧差商为 2.01，双侧差商 2.01/1.99，解析导数为 2。

抽样视觉复核查看了起始/中间/末帧：数学过程可见，但两点接近时标签存在挤叠，模型代码末步计数显示 3/4（应为4/4）；保留生成原件与检查记录，未把自动通过声称为教师或正式视觉验收。整体流程已能产出实际素材，模型生成质量仍有局限。

旧测试进程随后自动开始的重复梯度下降测试已主动取消，记录在 `live-/475c41bc/superseded-gradient.json`；其取消没有改变已完成导数结果。取消时验收脚本曾因计划为空报错，已修复该脚本处理。最终梯度下降使用修复后的产品代码单独验收于 `live-/fad5bf4d/`，不会混用重复任务的结果。

### 真实三维梯度下降示例

`live-/fad5bf4d/result.json`：已完成，累计 7 次实际请求，使用配置中的 deepseek-flash。候选、澄清问题、最终计划共3次请求，两个用户选择记录全部被落实，没有重复提问；代码经一轮修复后通过模型审核并实际渲染。视频90秒、960×540、VP9 WebM，1463个实际绘制帧、8,131,936字节。

目标函数为 `J(θ)=½(θ₁²+4θ₂²)−θ₁−2θ₂+3`，最小值点 `(1,0.5)`，最小值2。默认 α=0.2、初值 `(−2.2,1.6)`，40步计算结果约 `(0.9996,0.5)`，损失2。视频同时含三维曲面、实际负梯度路径、等高线、损失曲线、稳定与发散演示；8个参数涵盖学习率、迭代数、两个初值、两个视角、特征方向和对数刻度。

模型审核指出并修复了“特殊初值在不稳定方向误差为零时仍被误标发散”、负梯度箭头长度与梯度模不一致、字幕区外文本等问题。已抽样查看起始/中间/末帧。仍有生成质量限制：发散图纵轴上限会截断到40、末段自动学习率演示与滑杆静止位置不同、视角控件是镜头基准的偏移；详见原始 `quality_report.json`。这些限制未被当成教师视觉通过。

最终补充渲染测试 `final-gradient-render/render_report.json` 通过：参数检查加入合法中间值（旋转的−180°/+180°端点可能相同），并覆盖每个镜头的中点，避免漏掉只在某镜头生效的控件。8个控件均通过，实际再编码90秒视频；原交付视频及其哈希未覆盖。

### 示例文件与离线使用

可直接打开以下独立示例，源文件都保留：

- [导数交互页面](../../deliverables/visualizations-20260928/derivative/interactive.html)、[导数视频](../../deliverables/visualizations-20260928/derivative/video.webm)、[导数源码包](../../deliverables/visualizations-20260928/derivative/source_bundle.zip)。
- [三维梯度下降交互页面](../../deliverables/visualizations-20260928/gradient-descent/interactive.html)、[三维梯度下降视频](../../deliverables/visualizations-20260928/gradient-descent/video.webm)、[三维梯度下降源码包](../../deliverables/visualizations-20260928/gradient-descent/source_bundle.zip)。

已使用真实 Edge 通过 `file://` 打开两个交互 HTML，3/8个控件加载成功、数学指标返回正常，无页面脚本错误。见 `offline-html.json` 和 `offline-*.png`。共16个示例文件复制后逐项核对SHA-256，清单在 `example-delivery.json`。

最终本机服务和 worker 健康，两个真实测试已完成，重复旧测试已取消，没有遗留活动模型测试任务。见 `final-runtime.json`。新网页输入框最终布局在 `local-entry.png`；已有讲义/Beamer 数据库、审批及文件均保留。

## 调试中修复的问题

真实模型曾将问题的候选选项与已选答案混淆，反复询问已回答的方向/深度。现将最新决定和所有已选答案单独整理进模型上下文，要求返回完整决定 ID 回执，并对重复题目和决策覆盖进行有限重试校验。

模型一度重复编写宿主已有的播放/时间轴控件；现明确宿主提供这些功能，模型仅生成数学和视角参数，并在结构校验中拒绝保留名称。字幕改为最多 120 字、最多三行，避免超出视频画面。

早期浏览器测试失败分别源于测试谓词的 CSP 写法和离屏 iframe 截图等待；修正测试并实际滚动到交互区后，视频播放、参数变化和截图均验证通过，未放宽页面安全策略。

## 相关技术资料

运行方案核对了 [MDN Canvas captureStream](https://developer.mozilla.org/en-US/docs/Web/API/HTMLCanvasElement/captureStream)、[MDN MediaRecorder](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder) 和 [Playwright 网络拦截](https://playwright.dev/python/docs/network)。具体兼容性以本机 Edge 实测与本项目锁文件为准。
