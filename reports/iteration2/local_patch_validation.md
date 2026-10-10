# 严格局部补丁模块：54 项离线回归通过

本轮交付 [local_patch.py](D:/研究生阶段/数学教学agent/math-teaching-agent/src/math_agent/local_patch.py)、[独立提示词](D:/研究生阶段/数学教学agent/math-teaching-agent/src/math_agent/prompts/repair_local_patch.md)、[测试](D:/研究生阶段/数学教学agent/math-teaching-agent/tests/test_local_patch.py) 和真实 CH01 S04 失败的 [fixture 副本](D:/研究生阶段/数学教学agent/math-teaching-agent/tests/fixtures/local_patch_ch01_s04.json)。未修改 pipeline/domain；持久恢复与流程集成由独立任务负责。

接口为 `apply_local_patch(section, allowed_ids, reply) -> (new_section, evidence)`，schema 为 `LocalPatch`：

```text
section_id
replacements: [{unit_id, tex}]
calculation_updates: []
calculation_additions: []
uncertainties_append: []
calculation_limitations_append: []
```

正文替换必须精确覆盖每个授权目标一次。程序固定原单元 ID、kind、relates_to、顺序和所有其他字段；未授权正文不能出现在补丁中。更新核算必须按既有显式 ID 定位，保留原 unit_id 绑定，且该单元在授权范围；新增核算仅绑定目标、ID 不得冲突。原有核算没有更新则原样保留，不能删除或重排；旧疑点及限制只允许附加，section 与 unit 元数据保留。更新请求的既有非协议元数据也保留，是否为检查器支持的数据仍由后续检查判定。

核算请求字段遵循既有协议、每项 64 KiB、section 总量不超过 100；正文和说明有长度上限，额外字段严格拒绝。程序不执行模型、不规范化正文、不直接运行 SymPy；输出始终是 `APPLIED_UNCHECKED`，数学/规范化/教师审核状态为 `NOT_RUN`。

**54 passed in 3.77s**，首次运行全部通过。见 [日志](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/local-patch-tests-01.log) 和 [JUnit XML](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/local-patch-tests-01.xml)。

| 验证类别 | 本轮实际证据 |
| --- | --- |
| 离线范围/格式/不可变性 | 授权多目标、顺序、非目标内容和嵌套元数据、旧核算保留、更新原 ID/绑定、外来或重复 ID、容量与字段白名单、疑点只追加、禁止全局 TeX 结构操作 |
| 真实 S04 失败 fixture | 完整 repair-1 基线和原被拒绝 repair-2 响应按原文件哈希复制；实际 U03/U04 改动已核实。原完整响应及包含 U03 的补丁全部拒绝，测试没有裁剪 U03 后接受其余响应；复制时原三个文件字节未变 |
| 原有界符号核算器 | 54 项内的两项实际运行原 `check_math` 子进程：请求 `1+1=2` 为 PASS，`1+1=3` 为 FAIL。补丁模块本身不宣布数学通过 |
| 真实 API | NOT_RUN；测试命令及自动 fixture 清空 key、live=false、streaming=false，未导入 User 环境 |
| Windows 编译 | 本模块轮次 NOT_RUN；在 Windows 运行 pytest/SymPy 不等于 XeLaTeX 验收 |
| 教师数学/视觉验收 | NOT_RUN |

命令（环境已按上述隔离设置）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_local_patch.py -q --basetemp workspace/t/lp01 --junitxml reports/iteration2/local-patch-tests-01.xml
```

本模块是在 `ui-postfix-20260920-031401-721` 的五例 E2E 完成后新增，不属于那次 85 文件源码快照或先前 369 项本地测试快照。后续集成及 Windows 编译结果须由新的独立记录证明，不能将历史 PASS 外推到新代码。
