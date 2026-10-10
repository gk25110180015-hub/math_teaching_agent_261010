# 显式预算扩展与部分草稿交付验证

日期：2026-09-20。此项属于离线/浏览器整合验收；真实 API 调用与教师数学、视觉验收均 **NOT_RUN**。

## 实现与边界

- SQLite migration 002 持久化初始预算、用户覆盖值、版本号和动作审计。请求、单单元修复、全文修复分别计量。服务默认值不能覆盖已经记录的初值；调用方额外 hard cap 独立生效。
- 预算 API 仅允许本地用户对 `BLOCKED` 且无活动 job 的任务显式操作。需要当前预算版本/计划身份、严格整数、增加说明；重复 action_id 不能重复增额或改变内容。会话、CSRF、Origin 校验沿用本机 API 门禁。
- 扩额不清零请求和修复次数，不改变原审批、失败记录或产物，不排队、不调用模型、不代替教师审核。用户另点重试后 worker 才继续。普通重试不能提高耗尽的预算。
- 真正旧任务已有请求计数却没有预算基线时，显示 `UNKNOWN`，执行初始化、普通重试、仅修改修复预算均阻塞；不会采用普通服务的 120 请求默认值。用户明确填写 requests 并确认历史未知时，记录的是新的确认上限，审计不会冒称其为已知历史上限的增加。
- 保留的 benchmark state 可经显式本地方法核验导入历史请求上限：匹配文件 SHA、工作区、唯一 run_id、两处计数与数据库计数、两处上限，且必须无活动任务。只导入已有证据支持的请求上限，local/global 的历史值不伪造。导入本身不执行任务。本子任务没有调用该方法修改真实基准数据库。
- 部分章节只读下载经过检查点哈希、来源路径、run/section 归属、文件字节哈希校验。TeX、检查点 JSON、已有 PDF 均标记 `PARTIAL`；不进入教师审核记录。旧检查点未记录计划身份时显示 `UNKNOWN` 和保存时间/哈希；有确切记录时才区分 `CURRENT`/`STALE`。本次没有回填旧计划身份。

## 实际执行结果

| 分层 | 结果 | 证据 |
|---|---|---|
| 离线预算/API/迁移 | **55 PASS，9.26 秒**。含严格整数、并发/状态前置条件、幂等、审批/计数保留、hard cap、legacy 证据导入和拒绝、草稿篡改/外来路径阻断。单元 fixture 的 PDF 是合成字节，不能视为编译测试。 | [日志](budget-api-tests-02.log)、[JUnit](budget-api-tests-02.xml) |
| 真实浏览器 + mock provider + Windows XeLaTeX | **1 PASS，27.62 秒**。独立 Edge、服务/worker、临时端口 61387；模型密钥空、live/streaming false。实际编译后模拟耗尽计数，界面显式从 120 改为 121，再另点重试。 | [日志](budget-ui-20260920-03.log)、[JUnit](budget-ui-20260920-03.xml)、[结构化证据](budget-ui-20260920-03/20260920-040408/budget-flow-evidence.json) |
| 真实模型 API | **NOT_RUN**；上述 120 是隔离 fixture 中的合成计数，没有发出 120 次模型请求。 | [环境与端口](budget-ui-20260920-03/20260920-040408/context.json) |
| 教师数学/视觉审核 | **NOT_RUN**。最终状态是 `AWAITING_USER_REVIEW`，reviews 保持空。 | 同上 |

浏览器实际校验 2 个部分章节的 TeX/JSON/PDF，共 6 次 HTTP 200 和 SHA 匹配；保存预算后确认没有自动排队，原计数、审批、错误、jobs、artifacts、reviews 保持不变，刷新后同样成立。用户另点重试后生成 12 个新 artifact（其中 1 页 PNG、PDF、完整源码 ZIP），全部实际 GET 并核对 SHA；保留前一轮 12 个 artifact。控制台 pageerror 为空。截图与 trace 保留于 [该次目录](budget-ui-20260920-03/20260920-040408/)。UI 截图已检查预算表单及 `PARTIAL / UNKNOWN` 提示可见，不等于教师对数学或页面排版的验收。

关键截图：[阻塞与部分结果](budget-ui-20260920-03/20260920-040408/budget-blocked-partial.png)、[已扩额但未执行](budget-ui-20260920-03/20260920-040408/budget-increased-no-execution.png)。浏览器服务由 fixture 自行清理，没有启动或停止 8765/8766。

## 保留的失败证据

1. [首轮 API 日志](budget-api-tests-01.log)：6 PASS、36 fixture setup errors；fixture 没有声明 `trusted_input=true`，实际触发产品信任门禁。仅补正 fixture，没有降低门禁。
2. [首轮浏览器日志](budget-ui-20260920-01.log)：初次真实编译成功后，测试误读临时工作区的空数据库路径而失败。改为服务实际使用的 `runtime/w/agent.db`，原日志/截图/trace 保留。
3. [第二轮浏览器日志](budget-ui-20260920-02.log)：预算交互、部分下载及恢复已完成，最终复用单次构建 helper 按文件名查找报告，因两次构建的报告均保留而触发严格定位器错误。新测试改为按新增 artifact_id 核对所有新产物；没有删掉旧产物或修改产品代码。

产品代码在第二轮 API PASS 后冻结；上述两次浏览器 fixture 修正未改产品。独立只读复查确认旧 60→默认 120 的隐式放宽已阻断，七类错误历史证据拒绝、真实计数保留；审查的 `budget.py` SHA-256 为 `dae7e343b22ef63b1daeb3a4df2b9d478e5f211bd5d513c4388d12fd277bc76e`。

## 已验证的显式 legacy 导入调用方式

下面是供本地操作者核验后执行的调用方式；此报告本身不执行它。`expected_sha256` 必须采用已经核验并保留的状态文件 SHA，而不是无条件信任任意新文件。真实基准的请求上限应从证据恢复为 60；不修改 state，不重置 count，不提高任何任务预算。

```python
from pathlib import Path
from math_agent.service import Service
from math_agent.settings import Settings

service = Service(Settings(workspace=Path("workspace/iteration2-live"),
                           max_requests_per_run=60), actor="local_user")
result = service.import_legacy_request_budget(
    run_id,
    Path("reports/iteration2/live-lectures/benchmark_state.json"),
    expected_sha256,  # 已核验状态文件的 SHA-256
)
```

接口返回 `requests=历史上限`、原 request_count、version=0、source=`VERIFIED_BENCHMARK_STATE`。数据库已有请求基线、活动 job、过时计数或不一致证据会拒绝；不会用导入覆盖用户选择或开始模型请求。
