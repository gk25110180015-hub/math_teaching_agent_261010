# HTTP 200 流式 API 错误恢复

真实触发：CH02 请求计数128，全章接口审阅，provider.request事件2365与失败事件2370。HTTP200流中明确出现顶层error控制事件，旧程序以PROVIDER_RESPONSE停止，没有进入可用备用模型。旧记录保留361接收字节及wire SHA，但未保存原error对象，故不能倒推本次具体供应商错误码或错误文本。

候选仅改供应商流中的顶层error控制事件及其路由错误类型，不改变计划、教学响应schema、数学裁定或普通完成消息。实际数学issues、业务JSON结构错误、明确refusal、length与tool_calls的原守卫不变。显式policy/content_filter/moderation/safety/refusal或请求参数/上下文限制类型继续停止；其他API错误尝试剩余已配置模型，原默认模型不变。预算、取消和lease仍优先。

新错误先归档选取的有限诊断字段code/type/message/status/param（字符串最多2000字符），剔除任意附加字段和隐藏reasoning；两个已配置密钥均经原scrub清除。原事件及已接收wire字节保留哈希、请求身份和计费不确定性。部分教学内容不会成为备用模型的输出，也不会当成功保存。

实际隔离回归：`combined-recovery-validation/20260923-091907-824890`，157 PASS，1真实API排除，生产代码不变、外网尝试0，模型全为MockTransport。其中20项新增覆盖API错误→Flash、Flash失败→Pro、部分内容丢弃、诊断归档/隐私字段、单模型显式禁止fallback、明确内容/参数限制不切换和预算失败不可隐藏。原同类保护测试保留且通过。

此版本尚待停稳任务后部署。没有为了发布候选停止正在执行的第三章，也没有把旧失败改为成功；原具体SSE错误无法重现，模拟路由验证不得称为该真实事件已自动恢复。实际章节恢复另按原job证据记录。
