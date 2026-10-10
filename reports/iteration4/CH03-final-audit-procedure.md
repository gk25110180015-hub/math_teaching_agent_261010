# CH03 最终冻结、渲染和逐项审计流程

当前仅准备流程。没有对未定稿作最终评分，没有执行此处的最终冻结/渲染，教师数学与视觉保持 NOT_RUN。

## 进入条件与固定版本

协调任务给出“本轮最终成果已冻结”通知后才启动。只读取实际 `a45be503af594ce8aae0bb1e4c30184b` 的当前批准计划 revision 2 / hash `fbd172c8df0c12fca976e9067b04afe5210016559e210ca8dd0c3e7d37f3f1f7`，确认没有 queued/running build，且全章 5/5 节已经形成最终文件。AWAITING_USER_REVIEW 表示可供审计的完整草稿，不代表教师已通过。

使用只读 SQLite 快照记录 run/approval、当前未 superseded 的 PDF/TeX/ZIP/quality_report、各节检查点和全局审阅。检查点版本按 `created_at DESC,rowid DESC` 选择，并校验已批准 plan/spec/check contract 及输出/源码 SHA；不能按 input_hash 的字典遍历顺序挑版本。记录全部旧失败与新通过证据，ZIP 由协调任务在新目录实际重编译。

由协调任务明确提供最终 PDF、最终 TeX 的路径和 SHA；不要使用 glob 最新 mtime 或 `latest_build` 中间稿自行猜测。保存输入哈希、原批准身份、检查点与审阅输出，两个文件必须来自同一次最终 build。

## 实际可运行的只读冻结/渲染助手

[freeze_render_ch03_final.py](freeze_render_ch03_final.py) 只将明确给定的 PDF/TeX 复制到新报告目录，逐字节校验，提取物理页文字、TeX `% UNIT` 行范围，再用 Poppler 渲染全部物理页。它不发 API、不编译、不修改源文件，不生成教师签认，不根据文字提取自动判数学或视觉通过。失败日志和部分产物保留，拒绝覆盖已存在目录。

已确认此环境可找到 Poppler `pdftoppm` / `pdfinfo`，且项目虚拟环境有 `pdfplumber` / Pillow。只执行了助手语法/CLI 检查，最终渲染尚未执行。命令中的路径和 SHA 必须替换为协调任务冻结通知中的实际值：

```powershell
.\.venv\Scripts\python.exe reports/iteration4/freeze_render_ch03_final.py --pdf '<最终PDF绝对路径>' --tex '<同次build的TeX绝对路径>' --expected-pdf-sha256 '<冻结PDF SHA>' --expected-tex-sha256 '<冻结TeX SHA>' --output 'reports/iteration4/ch03-final-audit-唯一时间戳' --final-artifacts-confirmed
```

其中 `--final-artifacts-confirmed` 只确认协调任务已经冻结输入，**不是人工/教师通过标志**。输出 manifest 显式区分 `RENDERED_ALL_PAGES_NOT_VISUALLY_REVIEWED` 和 agent/teacher NOT_RUN。`page-review-ledger.json` 每页初始 NOT_ASSESSED；渲染成功本身不能升级视觉结论。

## 22 项语义与 G01–G08

沿用 [22 项条件占位](ch03-audit-preparation-20260920T154547210089Z/audit-preparation.json)，不改变分母。逐条记录最终 unit ID、TeX 文件 SHA 与行号、PDF SHA 与物理页、关键条件/推理及判断。3 项非必需拓展继续单列。原稿基准与本轮批准目标有范围差异时明确两者，不把字面不一致强制解释成错误。

特别核对：经典重要极限形式与已批准“常用基本极限”的范围差异；每个实际基本极限的弧度/定义域/先修与非循环证明；乘除等价替换、加减抵消辨析、阶基本思想；S02 夹逼例练；端点单侧连续；最值取得及介值/零点条件；经济模型计量单位、存在与唯一的不同前提。所有练习独立复算，答案末尾位置和回链在真实 PDF 中核对。

同时复核工作流正在做的实际全局修复：S03.U05 商替换条件/证明及例练衔接；S04.U03 单侧无穷极限量词与间断点包含未定义点的表述。尚未看到最终补丁前不预判 FAIL；未定义点表述可属于澄清，不必然是数学错误。S05.U22 布局变化和严格单调性唯一性反例应继续保留。

## 按 PDF 技能逐页目视

PDF skill 已读取：`C:/Users/kuogai/.codex/plugins/cache/openai-primary-runtime/pdf/26.905.11957/skills/pdf/SKILL.md`。这是只读审阅，不使用 PDF 作者标记，不编辑或重新导出原 PDF。

逐页打开所有渲染 PNG，按物理页填写页账本，检查正文、上下标/分数、公式右界、表格、标题与证明断裂、缺字、答案题号/回链和异常空白。缩略图仅定位，不能替代每页足够分辨率的检查；疑似裁切处放大复核。文本抽取、几何检查和编译通过不能替代 agent 目视。

最终报告把模型审阅、结构化数学核算、真实 Windows 编译、源码 ZIP 新目录重编译、agent 语义/视觉、教师数学/视觉分别记录。没有教师操作时，最后两项始终 NOT_RUN。若发现问题，按既有复检反馈与限定单元修复链处理，保留旧成果与失败记录后再冻结新版本，不覆盖旧证据。
