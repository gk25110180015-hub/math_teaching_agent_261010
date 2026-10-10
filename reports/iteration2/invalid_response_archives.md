# 无效模型响应的后续归档修复

先前 smoke 有一次无效 JSON 只保存 hash/结构错误，没有原始全文；该历史缺口无法补回。

应用供应商适配器现在支持任务专属 `provider-failures` 目录。今后 schema 不通过时，单独保存有界、脱敏、唯一文件名的响应文本；事件仅含路径、hash、字节数和错误类型。环境密钥与配置 SecretStr 的实际值均作脱敏，取消后不发布归档；已有失败文件不覆盖。此项保留的是收到的完整但无效文本，不声称恢复网络超时尚未收到的字节。

[最终离线测试](provider-failure-artifacts-v3.log)：33 passed，1 deselected。MockTransport 检查两次结构修复分别留下两个文件、正文可追溯、密钥不在文件/事件中、取消不写文件；并覆盖既有 SSE 与非流式协议。没有真实 API、TeX 或教师视觉测试。

保留两次测试启动失败：[路径误写](provider-failure-artifacts.log)，未运行测试；[系统临时目录权限](provider-failure-artifacts-v2.log)，2 passed / 31 setup errors。最终改用工程内全新临时目录，未删除或覆盖失败产物。
