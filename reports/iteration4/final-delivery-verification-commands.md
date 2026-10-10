# 最终第二、三章交付验收命令

准备状态：脚本已适配，本文件的真实产物验收命令**尚未执行**。请等本轮最终自动复检完成、两任务无活动 job，且已刷新 `reports/iteration4/live-lectures/CH02|CH03/comparison.json` 后执行。

`verify_live_source_bundles.py` 新增 `--output-dir`、`--build-dir`；旧 iteration2 默认保持兼容，报告名称增加随机后缀以避免同秒覆盖。显式目录必须是 reports/workspace 内尚不存在的子目录。源码包和原 PDF 的 artifact ID/SHA、comparison 原字节 SHA 及快照均保留。

`verify_live_delivery_ui.py` 新增 `--output-dir`，保留 `--output` 别名；新增 `--expected-delivery`，将浏览器验收绑定到前一份干净重编译报告中的同一任务、同一 ZIP/PDF artifact ID 和 SHA。当前页面预览与复核仅使用非 superseded 产物，历史链接与下载哈希另外核验。脚本只发本机 GET，不点击复检或人工审核，不调用模型。

在工程目录执行以下 PowerShell 命令；每次生成新的批次路径，不覆盖前次证据：

```powershell
$deliveryBatch = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 6)
$bundleEvidence = Join-Path 'reports/iteration4' ('final-source-bundles-' + $deliveryBatch)
$cleanBuild = Join-Path 'workspace/iteration4-delivery' $deliveryBatch
$uiEvidence = Join-Path 'reports/iteration4' ('final-delivery-ui-' + $deliveryBatch)

.venv\Scripts\python.exe scripts/verify_live_source_bundles.py --run-dir reports/iteration4/live-lectures --case CH02 --case CH03 --output-dir $bundleEvidence --build-dir $cleanBuild

.venv\Scripts\python.exe scripts/verify_live_delivery_ui.py --base-url http://127.0.0.1:8766 --state reports/iteration4/live-lectures/benchmark_state.json --case CH02 --case CH03 --output-dir $uiEvidence --expected-delivery (Join-Path $bundleEvidence 'report.json')
```

第一条是实际 Windows XeLaTeX 干净目录重编译，并比较原/重建 PDF 的各页文本、页数与链接数；它不宣称人工视觉验收。第二条使用真实 Edge 验证当前 UI、所有当前/历史 artifact 下载哈希以及前后任务状态不变；只保存首末页面预览截图，不等于教师逐页验收。两个脚本都不发模型 API。

离线脚本验证已通过，证据见 [delivery-script-offline-69e7d6b3/result.json](delivery-script-offline-69e7d6b3/result.json)：输出目录防覆盖、根目录拒绝、未完成合成输入保持 NOT_RUN、旧参数兼容、同批 run/hash/artifact ID 匹配及五种错配拒绝。旧 iteration2 重编译报告哈希未变。此验证**没有执行真实编译或浏览器**。

首次验证脚本因测试辅助代码使用系统 GBK 读取 UTF-8 报告而中断；该测试辅助问题修正后重跑通过，原失败证据保留在 [delivery-script-offline-175adf46/result.json](delivery-script-offline-175adf46/result.json)，未修改或覆盖旧验收结果。
