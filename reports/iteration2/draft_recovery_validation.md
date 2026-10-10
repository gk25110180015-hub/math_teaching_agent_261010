# 未审写作草稿恢复与 Windows 文件哈希修复

改动仅在 `src/math_agent/pipeline.py`，新增测试 `tests/test_draft_recovery.py`。没有发送真实 API 请求。

## 恢复边界

新增 `Pipeline.writer_draft(spec, context)`，在 writer 请求前检查 `runs/RUN_ID/draft-cache/SID.json`。缓存键包含完整 writer context hash、实际 writer 提示词文件 hash、WrittenSection JSON schema hash、模型和 provider；缓存指向当前 run 受控 build 目录中的不可变 `candidate.json`，并记录文件字节 hash。

只有上下文、提示词、schema、模型、provider、section ID、unchecked 状态、受控路径、文件 hash 和实际 schema 验证全部匹配时复用。任何变化／损坏／越界路径都重新生成，旧候选目录完整保留，替换索引前把旧索引存入 `draft-cache/history/`。

每次尝试创建全新草稿目录；复用时复制原始候选字节并保存 `draft-reuse.json`。**unchecked 不是 checked checkpoint**：归一化、内容／交叉引用、安全预检、局部数学工具、模型审阅和编译仍按原流程执行。缓存没有插入 Store.steps，也不会沿用旧审核结论。元数据写入受到原 job fencing 校验，过期 worker 不能覆盖当前索引。

修复前已经存在但没有该完整身份索引的草稿不会自动导入缓存；不能凭“同名 S01”猜测它使用的是当前提示词和上下文。修复中生成的候选仍是另行留存的修复证据，不被冒充为原 writer 输出。

## Windows checked checkpoint 的实际缺陷

新测试恢复成功后再次调用原 checked checkpoint 路径，发现仍重复检查。原因是原代码将 `digest(tex)`（内存 LF 字符串）存为 source_hash，而 Windows `write_text` 的实际文件含 CRLF；恢复却检查 `digest(read_bytes())`。两者自然不同。

离线 fixture 的实测：内存／read_text 归一化 hash 为 `5702252ba0437dc04d0bff09e094c72339ea933eccd5eaa24e380cf47d8e819e`，实际 19 个 CRLF 的文件字节 hash 为 `208f09dec235c992f0d31dd025e4f3b75a3ccc6a116f54379043bd61b90ac008`。在主任务授权后，source_hash 改为源码写盘后的 `digest(read_bytes())`。原 checked gate、缓存键、审批要求和 checkpoint 数量语义均保留。

旧 checkpoint 若存错 hash，仍按原失败匹配规则重新检查，不篡改历史记录使其伪装匹配。

## 实际执行结果

先红测试 `draft_recovery_red.log`：9 failed，复现缺少草稿缓存及审阅失败后重复 writer。首次实现后 8 passed / 1 failed，定位上述 Windows 哈希缺陷，日志保留为 `draft_recovery_windows_hash_failure.log`。

最终命令：

```powershell
.venv\Scripts\python.exe -m pytest tests/test_draft_recovery.py --basetemp workspace\draft_recovery_verified -q
```

结果 **9 passed in 1.32s**，日志 `draft_recovery_validation.log`。

- 模拟第一次 reviewer 超时后恢复：writer 总共只调用 1 次，归一化与数学工具各执行 2 次，reviewer 执行 2 次，成功恢复后才进行编译并写入 1 个 checked checkpoint。
- 再次恢复已完成章节：正确命中原 checked checkpoint，没有新增 writer／review／编译，也没有增加 steps 数量。
- 上下文、模型、prompt、schema 改变，候选文件 hash 损坏，schema 内容损坏和越界路径均触发新 writer 输出；旧文件保留。
- 普通调用方修改返回对象不会改写原候选；新尝试目录和 unchecked 标记保持独立。

测试使用**离线假 provider 和假 compiler**，真实本地 SQLite、Windows 文件读写及原 pipeline 编排。它验证恢复机制与调用次数，不证明真实供应商成功或 XeLaTeX 编译成功。真实 API、真实 Windows 编译、教师人工视觉验收在本子任务均为 **NOT_RUN**；实际后续 live 运行证据由主任务单独记录。
