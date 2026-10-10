# 真实审阅同题对照：v5 → v6

两版本各对三个模型运行相同的一正一负控制题。严格本地预期符合数从 **3/6** 变为 **5/6**。这是一组针对性回归；应结合下面的逐题识错与严重度记录阅读，不能直接称为模型总体准确率。

## 固定条件与判定

R01 的完整连续定义先给一般等价关系，随后追加两函数均趋零的条件，既有预期为正确，不应出现 review/blocking。R02 明确取消趋零条件却仍称等价无穷小，既有预期为错误且要求 blocking。预期均在本地比较，没有发送给模型。warning 不影响这组严格分类。

三个模型按 gpt6 → deepseek-flash → deepseek-v4-pro 顺序执行，每个模型先 R01 后 R02；本实验关闭自动降级以比较所选模型本身。gpt6 的请求及返回模型为 gpt-6-astra，启用 SSE、temperature=0.1；两个 DeepSeek 模型使用 thinking enabled、high、非流式。

## 逐模型逐题结果

| 模型 | 控制题 | v5 严格分类 / 严重度 | v6 严格分类 / 严重度 | 单题墙钟秒 v5 → v6 | 原始回复 |
|---|---|---|---|---|---|
| gpt6 | R01 | FAIL；review×1 / warning×1 | PASS；无问题 | 66.594 → 45.764 | [v5](live-review-controls-v5-20260920-1515/gpt6/R01-review.json) / [v6](live-review-controls-v6-20260920-1530/gpt6/R01-review.json) |
| gpt6 | R02 | PASS；blocking×1 | PASS；blocking×1 | 15.518 → 13.782 | [v5](live-review-controls-v5-20260920-1515/gpt6/R02-review.json) / [v6](live-review-controls-v6-20260920-1530/gpt6/R02-review.json) |
| deepseek-flash | R01 | FAIL；review×1 | PASS；无问题 | 62.745 → 39.540 | [v5](live-review-controls-v5-20260920-1515/deepseek-flash/R01-review.json) / [v6](live-review-controls-v6-20260920-1530/deepseek-flash/R01-review.json) |
| deepseek-flash | R02 | PASS；blocking×1 | PASS；blocking×1 | 22.005 → 25.252 | [v5](live-review-controls-v5-20260920-1515/deepseek-flash/R02-review.json) / [v6](live-review-controls-v6-20260920-1530/deepseek-flash/R02-review.json) |
| deepseek-v4-pro | R01 | PASS；无问题 | PASS；warning×1 | 109.621 → 141.693 | [v5](live-review-controls-v5-20260920-1515/deepseek-v4-pro/R01-review.json) / [v6](live-review-controls-v6-20260920-1530/deepseek-v4-pro/R01-review.json) |
| deepseek-v4-pro | R02 | FAIL；review×1 | FAIL；review×1 | 89.274 → 97.337 | [v5](live-review-controls-v5-20260920-1515/deepseek-v4-pro/R02-review.json) / [v6](live-review-controls-v6-20260920-1530/deepseek-v4-pro/R02-review.json) |

v5 的 gpt6 和 Flash 在 R01 都把连续定义的承接视为核心歧义，给出 review；按冻结的完整上下文预期，这是两个正例误报。gpt6 举出的两个趋零但不等价函数不满足前句已保留的等价前提，不能据此证明该完整定义有数学错误。Flash 的依据是读者可能不把前句当作持续前提，也属于这组条件承接回归针对的过度阻断。

v5 的三个模型都实际识别了 R02 错误。Pro 明确给出 p=q=1 的合法反例并指出“等价无穷小”不应取消趋零要求，但严重度仅为 review，所以未满足本地要求的 blocking。这是**识错但严重度不符，不是漏检**；真实工作流同样会保留疑点并要求处理。

v6 逐题结果解读：

- gpt6：R01 正确对照未被阻断；R02 识错且 blocking。
- deepseek-flash：R01 正确对照未被阻断；R02 识错且 blocking。
- deepseek-v4-pro：R01 正确对照未被阻断；R02 识错但仅 review。

## API、实际模型与时延

- v5：6 次真实请求、6/6 结构有效回复；首选、实际调用及回传模型标签 6/6 一致；HTTP 错误状态 未观察到；错误/结构修复记录 0 条；整轮墙钟 365.767 秒。
- v6：6 次真实请求、6/6 结构有效回复；首选、实际调用及回传模型标签 6/6 一致；HTTP 错误状态 未观察到；错误/结构修复记录 0 条；整轮墙钟 363.378 秒。

逐条核对首选 model_id、实际调用 model_id、requested_model 与 reported_model；结果详见 JSON 中每条记录。没有把备用模型的成功算作首选模型成功。每个版本的状态文件包含完整请求时序、结构验证与 usage；本报告未新增请求。上述时延没有控制供应商负载，不据此给模型速度排名或宣称提示词造成加速。

## 指纹与复现证据

| 证据 | raw SHA256 |
|---|---|
| [原始控制题文件](../iteration2/review-context-calibration-fixtures.json) | `3596ee97894637b949385f04ce6f51defd8a330e2f121aa313abb5fdb2a71dc7` |
| [v5 冻结提示词](live-review-controls-v5-20260920-1515/prompts/reviewer_math.md) | `db70a7e3b2a91f81157cb478f5a9b2c5edf2ca9a595c4f7cc28e5b9e6f96822b` |
| [v5 最终状态](live-review-controls-v5-20260920-1515/state.json) | `01d445fa861717326c0df01ecfc67a032021212005b2e1b0962a4c23e81b831e` |
| [v5 两题及本地预期快照](live-review-controls-v5-20260920-1515/fixtures-local-only.json) | `0fc6be0ea14687a91f5c93fb760ab203cba777144e3755344b828d00f239de56` |
| [v6 冻结提示词](live-review-controls-v6-20260920-1530/prompts/reviewer_math.md) | `cd75bbcf1516a0fa5ecaa882e753956e82d65da7e0640442db98717a1cf6f92d` |
| [v6 最终状态](live-review-controls-v6-20260920-1530/state.json) | `fd8aaf6c2ddb116a092176145bde202936f886ee079a20bcac19b5925dd3434e` |
| [v6 两题及本地预期快照](live-review-controls-v6-20260920-1530/fixtures-local-only.json) | `0fc6be0ea14687a91f5c93fb760ab203cba777144e3755344b828d00f239de56` |

已验证两版冻结题目与预期完全相同。JSON 另给每题独立 input/expectation 指纹及每份最终回复 raw SHA。provider 的 input_hash 实际覆盖整个 messages（含 system 提示词），所以 v5/v6 的该值不同是预期现象，不能据此认定题目改变。

## 解释边界

- 仅两个已知控制题、每模型每版本各一次；V6在读取V5相同题的反馈后修改。这是针对性回归，不是盲测、留出集或总体数学准确率估计。
- 没有模型权重训练。修改的是通用审阅提示词；两版本fixture与本地预期相同，预期没有发送给模型。
- 严格本地评分对负例要求blocking；真实工作流将review与blocking都作为未解决问题处理。严重度不符不能描述为模型漏检。
- 单题墙钟耗时包含网络、生成、结构验证及结果落盘，未隔离服务负载或采样波动，不能据两点推断性能提升或提示词的因果效应。
- reported_model是服务端返回标签，不是对供应商后台模型身份的独立鉴定。此次成功记录不保证未来API可用。
- 两题没有覆盖一般几何级数、部分和初值、完整章目标与PDF排版；不能据此宣称真实章节制作效果或人工数学/视觉验收通过。
- 未解析或传播模型隐藏推理；审读对象是归档的最终结构化回复。

人工数学与视觉验收均 NOT_RUN；这些文字控制题不包含 Windows 编译验收。
