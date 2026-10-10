# 提示词版本与失败请求追溯修复

2026-09-20。发现旧 provider 的成功事件将 `prompt_version` 固定写为1；实际提示词哈希可以区分成功调用的不同正文，但网络失败和无效JSON事件未记录独立提示词哈希。不能把旧版本字段当作准确版本号，也不能为缺失记录回填猜测值。

现在每次 `generate` 读取提示词时，从其版本头提取实际声明版本，连同提示词哈希和输出 schema 哈希，在发送前、有限网络重试、无效JSON和成功事件中记录。一次格式修复循环固定使用已经读入的提示词；期间文件落盘变化不改变该循环的元数据。无版本头时版本为 null，来源为 UNDECLARED。普通连通检查没有模板，不伪造模板版本。

基准报告保留这些字段，并区分 `declared_prompt_header`、`LEGACY_HARDCODED_NOT_VERIFIED` 和 `UNKNOWN_NOT_RECORDED`。旧事件不修改；旧成功调用保留其真实提示词哈希，旧缺失信息仍为未知。

**离线回归55 passed、1 real_api deselected，1.19秒**。见 [日志](provider-prompt-identity.log) 和 [JUnit](provider-prompt-identity.xml)。包括200成功、无效JSON、HTTP504、格式重试时模板文件改变、无版本头，以及旧/新混合事件报告。全部为模拟HTTP，真实API/Windows编译/人工验收均 NOT_RUN；新行为须由之后真实任务的事件另作验证。
