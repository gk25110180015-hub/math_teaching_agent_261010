# 三模型环境配置与 CLI 验证

2026-09-20。本报告仅覆盖环境脚本、CLI 和有界能力探针，不替代完整工作流或真实 API 验证。

- `Configure-LiveApi.py --provider deepseek` 使用隐藏输入，或显式非终端 stdin 管道；拒绝命令参数密钥。只写 Windows User `MATH_AGENT_DEEPSEEK_API_KEY` 与 `MATH_AGENT_DEEPSEEK_API_BASE_URL`，不改旧 gpt6 或 live 开关。每次生成独立配置证据，旧报告不覆盖。
- `Common-Windows.ps1` 补入新增两个 User 变量，已有 Process 值优先。所有非 live 的 `Test-Windows.ps1` 套件临时清空两密钥并禁用 live，结束后恢复 Process 环境。
- `provider check --live --model <ID> --no-fallback` 可单独检查三个模型。成功能力依据实际成功请求的 `model_id` 归属，缺少模型身份不能标记通过；失败和每次请求保留独立记录，不把 fallback 的 DeepSeek 成功写成 gpt6 成功。
- `verify_model_capabilities.py --execute-live` 顺序为 gpt6、deepseek-flash、deepseek-v4-pro，各自关闭 fallback、网络重试和结构修复，最多三个实际 HTTP 请求。没有执行开关时记录 NOT_RUN，甚至不读取 Settings 凭据。一个模型失败仍继续独立测试下一个。
- 13 项离线回归通过，0 个真实 API 请求、0 个 Windows XeLaTeX 编译、0 次人工视觉验收。测试使用 fake provider / offline configuration；不能据此声称三个远程模型均可用。

证据：[最终日志](config-cli-offline-20260920-2.log)、[最终 JUnit](config-cli-offline-20260920-2.xml)。先前 11 项快照保留在 `config-cli-offline-20260920-1.log/xml`，两者重叠，不相加。

DeepSeek 的参数与三个模型名称已核对[官方思考模式文档](https://api-docs.deepseek.com/guides/thinking_mode/)及 [Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/)。本应用不用远程 tools 参数，仅保留最终 content，不记录或回传 reasoning_content。模型价格仍为 unknown/null，本轮不涉及权重微调。

本机实际隐藏输入配置由主任务完成，具体证据为 [DeepSeek 环境配置](environment-deepseek-20260920T030536-775c665d.json)。真实三模型连通、工作流、编译及 UI 验证在独立报告中列出；这里未执行。
