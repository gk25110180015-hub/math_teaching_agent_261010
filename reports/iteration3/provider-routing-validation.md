# 多模型 provider 与故障切换验证

状态：定向离线测试通过。此报告不代表真实 API、Windows 编译或人工视觉验收通过。

已实现固定界面 ID `gpt6`、`deepseek-flash`、`deepseek-v4-pro`。默认 `gpt6` 保留原模型名、API 地址与密钥设置。DeepSeek 共用独立环境变量密钥，分别发送同名模型，固定 `thinking.type=enabled`、`reasoning_effort=high`、`stream=false`，不发送 temperature。响应只读取 content，不读取、归档或回传 reasoning_content。

用户首选在每次独立业务调用中优先，其他候选按固定顺序。多个候选已配置时，HTTP 408/429/500/502/503/504、网络和读/连接/单次总超时会立即切换，每个候选最多一次。401/403/404也可跨候选切换，但不重复同一无权限候选。单候选或显式禁用切换时保留原有限 HTTP 重试。400/422、内容拒绝、截断、schema、数学错误、取消、租约或预算错误不通过切换绕过。

全部候选调用失败抛出 PROVIDER_ALL_UNAVAILABLE，供工作流保存可恢复阻塞状态。不会回退到 mock，不改任务模型选项，不提高请求预算。每次发送前调用既有计数/围栏函数。单次 HTTP 有总时间限制，多候选最多三个发送；结构修复预算与单候选网络预算仍分别约束。

结构修复固定在此前返回内容的模型；下一次正常业务调用重新优先用户首选。部分 SSE 响应发生超时时丢弃，不能成为替代模型输入或交付内容。call_id/model_id/preferred_model_id/requested_model/reported_model/base_url和参数用于每次请求归属；路由事件独立带 event，不冒充 HTTP 请求。模型返回的 model 缺失时不编造。

所有配置密钥与环境变量中 MATH_AGENT_*API_KEY 值都参与脱敏，包括响应正文、错误归档、JSON 转义诊断、反馈和事件元数据；公开配置仅有 key_configured/configured 状态。

| 验证 | 结果 | 证据 |
|---|---|---|
| 首轮路由与既有 provider 离线回归 | 90 passed，1 real_api deselected，2.14 秒 | provider-routing-targeted-01.log / .xml |
| 增补 SSE/结构修复边界及多模型工作流 | 102 passed，1 real_api deselected，2 warnings，3.54 秒 | provider-routing-targeted-02.log / .xml |
| 真实 API | 此定向测试未执行；由根任务另测 | 不据此声称真实可用 |
| Windows TeX 编译 | 此定向测试未执行 | provider 变更未运行编译 |
| 人工视觉验收 | 此定向测试未执行 | 浏览器验证由单独报告记录 |

两轮结果存在覆盖重叠，不能相加。首轮与第二轮源码产品接口一致，第二轮只增加两个边界测试和工作流测试集。

产品文件 SHA256（定向第二轮完成后）：

- provider.py: ccdc7b2f3ff58bab30193e3c1db809b8a203a2986f6096a8bfa5d30426daf5d6
- settings.py: 97848d0faa36342e1bd9a1f16c1b9cfacf97008ff0c9846e8ca5d8a8d1525cd0
- model_routing.py: 81ea797f095f6ace62f999d3391db2a55e9fc2ce5e40db38d132409eb099530a
- util.py: 1586d0ad75ca6fae49972e5eac763c4bd1ec118a8baaaeb7c7067df0fa98aa2d
- test_model_routing.py: a2a07f7b0773ea33739058ce05366ae338bec279671a53f909bd09eac7a47304
