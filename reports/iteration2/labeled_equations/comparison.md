# 带标签无编号公式：真实稿件引用修复

2026-09-20。本项未调用 API。使用此前实际 API 返回的 S01/S02 原始候选，重新执行本机 Windows XeLaTeX 编译。

原问题：S01.U05 在 `\[...\]` 内定义 `eq:reciprocal-limit`，S02.U09 和 S02.U12 用 `\eqref` 引用它。原稿可以编译成功，但 `.aux` 的目标锚点为 `definition.1.3`，PDF 两处链接错误地跳到例题。

修复只把这一个公式的 `\[`、`\]` 改为 `\begin{equation}`、`\end{equation}`。两定界符之间的数学正文、标签、空白、标点均逐字保留，来源与正文 SHA256 记于 [comparison.json](comparison.json)。编号公式的真实锚点变为 `equation.1.1`，显示编号 `(1)`；PDF 第 4 页两处链接均解析到此公式锚点。

| 验收项 | 修复前 | 修复后 |
| --- | --- | --- |
| 两节实际 Windows XeLaTeX 编译 | PASS | PASS |
| PDF 页数 | 5 | 5 |
| PDF 全页渲染 | 5/5 | 5/5 |
| PDF 几何检查 | PASS，0 issue | PASS，0 issue |
| `eq:reciprocal-limit` 目标 | `definition.1.3`（错误） | `equation.1.1`（正确） |
| 第 4 页实际链接数量 | 2，均错指例题 | 2，均指向公式 |

新增回归先红：13 failed / 7 passed / 1 deselected。修复后的纯逻辑回归：36 passed / 2 Windows tests deselected。最终包含实际 Windows 编译的定向回归：**38 passed，12.38 秒**。第一次实际测试因测试代码引用未安装的 `pypdf` 失败，已保留该目录；随后改用工程已安装的 `pdfplumber`，未增加依赖。

适用边界：仅处理当前节唯一、合法、显式的单个标签，且无嵌套显示数学、无 `\notag`/`\nonumber`。无标签公式、已有 equation 和显式 `\tag`/`\tag*` 均保持原样。多个标签、重复标签、动态/非法标签、分组内标签、嵌套显示数学等保留整单元并 BLOCKED；跨节唯一性继续由独立交叉引用检查负责。规范化幂等，单元 ID、关联和计算请求不变。

修复前后 TeX/PDF/aux/日志分别保存在 `before-compiled`、`after-compiled`，原始捕获文件和哈希保存在 `before`。全部 10 页已渲染；实现者查看修复后全部 5 页及修复前第 2 页，确认公式右侧出现 `(1)`、数学内容未变、引用可读。此项不替代教师审核：**教师人工验收 NOT_RUN**。

本项代码与测试落盘后已通知主代理更新已检查缓存版本，并通知环境与浏览器代理进行后续集成回归；未更改 pipeline 或写作提示词。
