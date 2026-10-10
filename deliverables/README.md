# 可独立查看的合成示例交付

这两份文件是浏览器端到端测试产生的 **MOCK／合成示例**，内容与规划未调用真实模型 API。PDF 均已在本机 Windows 11 使用真实 XeLaTeX（TeX Live 2024）稳定编译两遍；不是 mock PDF。

| 示例 | PDF | 完整可重编译源包 | 当前状态 |
|---|---|---|---|
| 数列极限讲义（1 页） | [lecture.pdf](mock-lecture/lecture.pdf) | [source_bundle.zip](mock-lecture/source_bundle.zip) | AWAITING_USER_REVIEW |
| 合成 TeX 转 FDU Beamer（5 页，含 overlay） | [slides.pdf](fdu-source-demo/slides.pdf) | [source_bundle.zip](fdu-source-demo/source_bundle.zip) | AWAITING_USER_REVIEW |

每个目录另有主 TeX 和原始 `quality_report.json`。数学审查仍为 NEEDS_REVIEW；FDU 正文区域接壤风险、讲义语义决策落实也保留相应复核状态。**教师人工视觉验收 NOT_RUN，正式教学验收 NOT_RUN**；不能据此认为教材内容、所有页面或真实 API 已通过验收。

`manifest.json` 记录任务／revision、原 artifact ID、源哈希、复制后哈希、真实编译引擎、PDF 页数及 ZIP 成员哈希。已验证两份 PDF 可打开、两份 ZIP 的 CRC 和安全成员路径、源包内容与原编译清单一致。主 TeX 与源包中的对应文件逐字节相同。只复制受控 PDF、主 TeX、ZIP 与质量报告；没有复制数据库或整个工作区。

重编译时先将源 ZIP 解压到新目录，使用已安装的 XeLaTeX 对 `lecture.tex` 或 `slides.tex` 连续编译至少两遍。FDU 示例的主题、字体适配文件和图片依赖在 ZIP 内；仅复制单个 `slides.tex` 不包含这些依赖。无需模型密钥。主题及素材沿用原始参考资源，示例仅用于本地私人审阅，不作公开分发授权说明。

此整理步骤仅核验现有 PDF／ZIP 并复制文件，没有重新调用 API、修改源模块或启动服务。重新编译源包的 Windows 验证另见 `../reports/delivery_validation.md`。
