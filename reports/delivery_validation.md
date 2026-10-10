# M5 本地交付验证

执行日期：2026-09-20。Windows 11 build 26200、本机项目 `.venv` Python 3.12.4、真实 XeLaTeX TeX Live 2024。原始三章材料没有修改。

```powershell
& .venv\Scripts\python.exe -m pytest tests/test_delivery.py --basetemp workspace\test_delivery_m5_01 -q
```

实际结果：**3 passed in 12.62s**。完整日志为 `reports/delivery_validation_initial.log`，机器可读汇总为 `reports/delivery_validation.json`。具体 PDF、每轮编译日志、全页 PNG、编译结果 JSON、交付证据 JSON 均保留在 `workspace/test_delivery_m5_01/`。

| 用例 | 实测结果 |
|---|---|
| T59 完整源包干净目录复现 | PASS。通过 glob 定位已有 mock 讲义工作流产出的 ZIP；使用受控 safe_extract_zip 解压 lecture.tex 和 README.md 到全新中文/空格/括号路径；独立两轮编译通过，PDF 1 页全部渲染。解压后可编辑源文件的哈希在编译前后保持一致。 |
| T49 预览 PDF 占用 | PASS。使用 Windows CreateFileW 打开第 1 版 PDF，仅允许读共享；先实测拒绝写入，再保持句柄开启，生成第 2 版至全新目录。旧 PDF 哈希未变、新 PDF 成功且路径/哈希不同；新 PDF 1 页全部渲染。 |
| T55 源包不泄漏密钥 | PASS。测试环境设置 synthetic sentinel，源码旁额外放置含该 sentinel 的 .env、SQLite、JSON 私有文件；调用真实 Pipeline.export_source，逐一读取 ZIP 的解压成员并扫描导出旁文件，未发现 sentinel，私有文件均未进入源包。实际供应商请求数为 0。 |

T59 本次确实使用已有工作流产物（非 fallback fixture）：源 ZIP SHA-256 为 `3a13ede99c9cc87f8cf1e7ce59bbb3cf731401449f19747934388af88930ead4`。完整原产物路径保存在 JSON，测试不写死易变化的 run ID。若独立干净测试环境没有历史包，测试会通过实际导出函数建立明确标记的合成 fixture，报告其不同来源。

真实 API：**NOT_RUN**，本组是 mock 内容与真实 Windows 编译/文件交付测试。教师人工视觉验收：**NOT_RUN**。全页自动渲染不能替代教师审阅；本组结果不表示三章真实讲义和双模板验收全部完成。
