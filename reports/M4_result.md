# M4：排版与全部页证据

已实现四档字号、可配置可见文本预算、完整单元合页、按完整句子/段落/item与数学环境拆页、连续假设重复上下文、题解pause、六类block、三态完整一级目录及超长目录分组。排版候选按合法字号后语义拆分，保留全部失败候选；不可拆公式不会截图/缩放/删除。

真实编译2–4轮，辅助文件稳定/日志门禁；本次PDF及新路径校验，旧PDF不能冒充成功。每个物理页面由无密钥PDF子进程渲染，真实 nav 建立frame/overlay映射；检查中间overlay，结合编译溢出与页面几何。

实际参考页又暴露“非当前overlay文字”的抽取边界：首overlay的题解被PGF移到页外，渲染图只显示题干，下一overlay显示原位置题解。这类对象不能与可见裁切混为一谈；只在真实nav同frame的另一个overlay能对应验证其文字和位置时才标记为隐藏对象。未知越界仍阻塞，真正中间overlay溢出fixture继续验证，具体修复证据见PDF检查报告。

主题probe另测四档有效字号、标题/导航/页脚与正文marker。`measured_probe`只对模板hash匹配时启用，不能称所有复杂三章版式已校准。详见 `layout_probe_validation.md`（及 JSON/probe产物）、`compiler_math_validation.md` 与 `reference_matrix.md`。

首次 FDU probe 发现导航顶部裁切，已记录并修复适配层，原sty不改；之前失败probe保留。自动渲染或几何PASS不等于教师视觉PASS。界面提供每页hash、overlay、问题与人工操作；存在阻塞错误不能用“通过”按钮绕过。普通非阻塞语义/视觉疑问须审阅全部页面和质量报告后发布。

真实模型视觉：NOT_RUN（能力未验证、未发送图片）；教师逐页视觉：NOT_RUN。三章完整发布仍受原文引用/实际版式问题及审核条件约束，详见最终矩阵。
