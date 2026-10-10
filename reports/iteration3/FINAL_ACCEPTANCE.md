# 三模型接入、故障切换与验收

记录日期：2026-09-20，Asia/Shanghai。**三模型已经配置并接入运行中的独立应用。** 三个模型的独立文本连通测试通过；同题数学审阅六例中五例符合本地预期，Pro的一项正确对照仍需复核。教师验收未执行，不能据此称完整数学教学质量全部通过。

## 当前配置与使用

[默认应用](http://127.0.0.1:8765)与[此前真实章节任务](http://127.0.0.1:8766)均已重启加载配置，服务及worker正常。模型已配置时，新建页面默认真实API和gpt6；三项均可选，未选择模型时使用gpt6。

|显示名称/稳定ID|实际请求model|接口根路径|参数|
|---|---|---|---|
|gpt6|gpt-6-astra|https://oneapi.advancedsolver.com/v1|保留原配置及SSE|
|deepseek-flash|deepseek-flash|https://api.deepseek.com|thinking.type=enabled、reasoning_effort=high、stream=false|
|deepseek-v4-pro|deepseek-v4-pro|https://api.deepseek.com|thinking.type=enabled、reasoning_effort=high、stream=false|

新密钥仅写入Windows当前用户环境变量 MATH_AGENT_DEEPSEEK_API_KEY，根路径为 MATH_AGENT_DEEPSEEK_API_BASE_URL。gpt6原密钥、根路径和模型变量保留；应用只读环境，不保存到源码或.env。[新增环境配置记录](environment-deepseek-20260920T030536-775c665d.json)不包含密钥值。

本轮核对了[DeepSeek思考模式参数](https://api-docs.deepseek.com/guides/thinking_mode/)和[Chat Completions接口](https://api-docs.deepseek.com/api/create-chat-completion/)，并使用真实请求验证。程序只使用最终content；reasoning_content不进入任务日志、源包或后续消息。配置步骤、独立模型检查和启动命令见[README](../../README.md)。

## 实际接入的切换行为

- 用户首选先调用，其余模型按gpt6 → deepseek-flash → deepseek-v4-pro的固定优先级排列。例如选Pro时，顺序为Pro → gpt6 → Flash。
- 对HTTP 408/429/500/502/503/504、连接/读取/总截止时间失败，以及某模型401/403/404，保留失败记录后尝试其它已配置模型。多个候选时每个至多一次，不先在失效首选上连续耗费三次。仅有一个可用配置时保留有限HTTP重试。
- 临时切换只作用于当前业务调用，后续调用重新优先用户所选模型，不改写输入、计划、审批或检查点。
- JSON格式修复仍沿用产生该响应的模型；数学疑点、拒绝、输出截断、取消、租约与预算问题不能靠随机换模型清除。全部候选调用失败时明确BLOCKED并保留恢复现场，不无限循环，也不悄悄换成MOCK。
- 每次HTTP尝试在发送前计入原请求预算。事件记录首选ID、实际路由ID、请求model、供应商报告model、call_id、接口、参数及原因；纯切换通知不冒充HTTP请求。界面区分最近尝试与最近通过结构校验的返回。
- 模型选项进入输入哈希和新计划；旧任务缺少model_id时只读解释为gpt6，不改写历史。草稿保留实际模型来源；源码交付清单分开记录首选与实际调用过的模型。

## 真实API验证

### 三模型独立连通

严格按gpt6 → Flash → Pro，每模型一次，关闭fallback及重试，**3/3 PASS，3次真实HTTP请求**。只有本模型成功才记本模型通过。见[汇总](model-probes-20260920-0315/summary.json)。真实能力记录分别保存于reports/model-capabilities，UI不会把“环境已配置”当作即时连通通过。

### 同题数学审阅

使用已有中性样例R01正确对照、R02错误定义，每模型各两次，请求只包含题目与上下文，本地预期不发给模型。提示词v4已冻结，未修改校准题目或重复抽样直到通过。**6次真实请求均返回可验证JSON；5/6符合本地预期，整体NEEDS_REVIEW**。见[全部状态及请求](live-review-controls-20260920-0317/state.json)。

|模型|正确对照R01|错误对照R02|本次耗时，秒|
|---|---|---|---|
|gpt6|符合预期|识别错误，符合预期|11.865 / 14.834|
|deepseek-flash|符合预期|识别错误，符合预期|50.593 / 12.755|
|deepseek-v4-pro|提出review，未符合正确对照预期|识别错误，符合预期|229.586 / 57.648|

Pro对“函数等价关系”的定义域提出额外复核意见。按本地校准预期属于误报；[原始审阅](live-review-controls-20260920-0317/deepseek-v4-pro/R01-review.json)完整保留供教师判断。API本身正常返回，此问题不记为网络失败，也不会通过换模型抹除数学疑点。以上是小型针对性回归和本次延迟，不是课程准确率、随机盲测或服务性能保证。

### 混合故障切换验证

另执行[混合验证](mixed-live-fallback-20260920-0326/result.json)：本地为gpt6注入HTTP504，然后让生产provider实际调用DeepSeek Flash成功。**PASS：1个模拟504、1次真实Flash请求**。这证明实际备用接口与生产路由可协同工作，但不宣称本轮gpt网关真实发生了504。未修改任务数据库或章节预算。

本轮以上验证共**10次真实API请求**（3连通+6数学+1混合备用），模拟故障另计。费用仍未知，不据请求数推算价格；不与旧讲义118次混算。

## 本地、Windows与浏览器测试

|类别|执行结果|证据和边界|
|---|---|---|
|最终完整本地回归|600 PASS，0 FAIL，0 SKIP，1 real_api deselected|[完整报告](local-final-20260920-113521.md)，212.51秒；120个源文件/测试/配置等前后SHA一致。模型HTTP使用模拟/替身，真实API另列；浏览器另测，不与专项相加|
|完整回归内Windows编译相关检查|20 PASS|真实Windows XeLaTeX及产物断言，包含预期编译失败、取消、越界写入限制和排版阻断；不表示20份PDF均编译成功。逐项用途见上述完整报告|
|provider/路由专项|102 PASS，1 real_api deselected|[报告](provider-routing-validation.md)。含与root工作流重叠测试，不与完整套件相加|
|工作流/恢复/预算/模型来源专项|首轮59 PASS/1 FAIL，修复后60 PASS|[首次失败](root-integration-01.log)、[通过](root-integration-02.log)。修正首选模型名缓存为随配置读取，模型变化必须使草稿缓存失效|
|环境配置/CLI专项|13 PASS|[报告](environment-cli-validation.md)。模拟注册表/传输，不冒充实际API|
|新增三模型Edge回归|5 PASS|[UI报告](MODEL_UI_VALIDATION.md)。真实浏览器、本地API、SQLite、Worker，供应商为MockTransport；覆盖三种选择、刷新与504→503→Pro成功，三次请求全部计数|
|原有Edge工作流回归|6 PASS，85.83秒|[日志](existing-browser-20260920-1116.log)。实际Windows编译，模型MOCK；包括预期编译失败与恢复|
|已部署UI桌面/手机|PASS|[只读报告](model-ui-final-readonly-20260920-1120/report.json)，1440×1100及390×844；三模型/默认/顺序，无横向溢出或JS异常，未触发模型调用|
|教师数学与视觉验收|NOT_RUN|agent截图检查及自动测试不代替教师审核|

首次完整回归为[598 PASS / 2 FAIL / 1 real_api deselected](local-final-20260920-111743.md)，120个文件前后SHA一致；旧交付fixture未提供新增来源审计所需的Store，另一个30毫秒deadline测试在完整套件中使第二模型也超时。已保留全部失败并修正夹具：交付fixture提供真实SQLite上下文，[3项专项通过](delivery-fixture-02.log)；截止时间测试使用真实2秒deadline，显式验证首选请求取消及Flash接管，[31项通过](provider-routing-deadline-fix-03.log)。后两项未修改产品行为。

第二次完整回归为[599 PASS / 1 FAIL / 1 real_api deselected](local-final-20260920-112433.md)，120个文件前后SHA一致。失败是已捕获CH02样例的实际SymPy核算返回not_checked，原断言未打印原因；随后同输入[10次离线重放及3次独立子进程诊断](numeric-diagnostic-20260920-113009-490177.json)均正常，[相邻用例三轮各55项](numeric-order-20260920-113312-336169/summary.json)也均通过。仅为该测试补充真实子进程输入、退出码、stdout/stderr及完整断言诊断，保留原8秒期限与全部预期；最终完整回归该项通过。该次失败原因仍未定位，不能据后来成功认定已修复，也不把UNKNOWN改判为PASS。详见[调查及最终子进程诊断摘要](numeric-unknown-investigation.md)。

最早新增浏览器夹具在Playwright同步桥线程中执行Worker造成asyncio事件循环冲突，HTTP模型请求为0；修正为独立线程后5项通过，原trace/截图/DB保留于UI报告。上述失败均未倒改为PASS。

## 运行状态、原任务与交付边界

重启前确认两个工作区均无queued/running任务；重启后比较runs、jobs、审批、计划、步骤、产物、reviews与预算表摘要，**全部一致**。见[重启前](runtime-before-restart.json)、[重启后](runtime-after-restart.json)；[交付前只读复核](runtime-final-readonly.json)再次确认两服务与worker健康、任务表不变。旧smoke/CH01/CH02/CH03请求仍为21/37/33/27；没有增额、重试或代签教师。上一轮第二、三章的局部修复预算问题仍需独立处理，新增API不清空已有预算。

原课程资料未作为本轮写入目标；原讲义、完整原稿和交付源包保留。[最终53份清单内原件SHA复核](originals-recheck-20260920-113945-235484.json)全部一致，该核对范围不包含清单之外后续新增文件。[此前文件交付](../iteration2/DELIVERABLES.md)继续有效，未用新模型覆盖旧稿。

[两组当前密钥的精确落盘检查](secret-storage-models-20260920-0320.json)：37144个允许类型源码/文本/报告/SQLite/WAL/SHM文件中匹配0、不可读0，PASS。范围是扫描时项目文件中的UTF-8/UTF-16字节，排除了依赖、git/cache和压缩文件；不扩大为全盘或任意编码审计。

完整课程M5教师验收仍未完成；本轮交付的是已经运行和验证的三模型选择、配置、来源记录及有界故障切换功能。
