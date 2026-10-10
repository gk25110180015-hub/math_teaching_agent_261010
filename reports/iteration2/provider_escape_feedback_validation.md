# JSON 转义纠错反馈：最小改进与离线验证

实际 CH02 S03 三份完整响应含未双转义的 TeX 反斜杠，最后两份内容相同。原产品已正确严格拒绝，但反馈只有首个 JSONDecodeError 的位置和通用说明，没有精确片段和同一响应中的后续非法转义。

本次仅修改 `src/math_agent/provider.py`，新增 `tests/test_provider_escape_diagnostics.py` 及三份原失败归档的只读复制 fixture；未修改 prompts、pipeline 或真实数据库。

新增字符串词法诊断仅辅助下一次模型结构纠错：

- 正确跳过 JSON 的成对反斜杠、转义引号、斜杠和标准字符转义；校验 `\uXXXX` 四个十六进制字符，标出非法或不完整 Unicode 转义。
- 使用 `JSONDecodeError.doc`，坐标与 strip/Markdown fence 处理后的标准 JSON decoder 文档一致。offset 是零基 Unicode 字符索引，行列为一基；非法 Unicode 的 offset 按标准 decoder 指向 `u`，另保留 escape_offset 指向反斜杠。
- 最多扫描 262144 字符、报告 20 项；每项片段最多 64 字符，完整序列化诊断最多 12000 字符。达到扫描或条目边界明确标 truncated，不把边界误判为非法输入。
- 配置/环境密钥及通用凭据模式先按原长度遮盖，再切片段，避免跨片段边界泄漏；重叠密钥按长到短处理。事件中只记录诊断版本、项数、截断标记和 hash，不记录正文片段。
- 提示附由 `json.dumps` 生成的合法 JSON 示例，并把片段明确标为不可信数据。原响应没有自动加反斜杠、补尾、改内容或宽松解析；仍须严格 `json.loads`、schema 校验及后续数学/编译检查。
- 未增加 schema 修复次数、网络次数、run 请求或调用者 hard cap；外部 BUDGET_EXHAUSTED 照常立即中止。

## Before / after 证据

| 日志 / XML | 结果 |
|---|---|
| `provider-escape-before` | 16 FAIL；先红测试记录旧版本缺少定位全部转义的能力。 |
| `provider-escape-after` | 56 PASS、1 real_api deselected；精确诊断及原 provider/HTTP/SSE/归档/提示身份回归。 |
| `provider-escape-final` | **77 PASS、1 real_api deselected，1.41s**；增加扫描边界、重叠凭据、schema 预算 0/1、外部请求预算与基准指标兼容性。 |

三份真实归档通过 MockTransport 完整回放，分别报告 3、2、2 处非法转义；首份 offset 3611/6353/6419，后两份 6353/6419。原响应逐字保留，三次仍严格失败，归档仍为三个独立不可覆盖文件，没有产生虚构的 schema 成功。两个修复请求的实际 mock 消息中包含全部定位、精确片段和合法序列化例子，事件不含正文。有效转义零误报，多行/中文坐标与标准 decoder 一致。

原始归档 SHA、诊断示例和最终 provider/test SHA 见 `provider_escape_feedback_validation.json`。本次使用独立 `workspace/t/je0`、`je1`、`je2`，显式关闭真实 API；测试内所需供应商响应全部是 MockTransport。

**真实 API NOT_RUN，Windows 编译 NOT_RUN（本次仅 provider 改动），教师验收 NOT_RUN。** 此前 517 项全量成功快照早于本补丁，本次以 77 项相关定向回归补充，不把它记作已覆盖新代码的全量成功。

正在运行的 CH01 进程此前已导入旧 provider，继续执行旧实现，不能据本次离线结果宣称已影响它。后续新 CH02 进程才会导入新反馈；模型是否实际遵循改进反馈，仍需主任务之后的独立真实运行证据。
