# 第二轮讲义与课件交付清单

## 真实 API 讲义草稿

以下 smoke 使用指定真实 API，2节/19单元/5页，状态 `AWAITING_USER_REVIEW`。自动 content/math/compile/layout/security PASS，policy NEEDS_REVIEW；教师数学与逐页视觉验收 NOT_RUN。它是独立小型测试，不替代正式三章。

| 案例 | PDF | 主 TeX | 完整源码 ZIP | 独立新目录重编译 |
|---|---|---|---|---|
| 数列极限两节 smoke | [PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/426866cf71d2437b/va8ac3987158b/build/lecture.pdf>) | [lecture.tex](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/426866cf71d2437b/va8ac3987158b/source/lecture.tex>) | [source_bundle.zip](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/426866cf71d2437b/va8ac3987158b/source_bundle.zip>) | [PASS：5页及逐页文字/链接数一致](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/live-zip-recompile-20260920-034007.json>) |

原 PDF SHA-256：`da08307ba65b8cee1ae259fade77d05d2e2195412ea9bdae3684a58aa8df7605`。ZIP SHA-256：`152d785ac8ca20c643c0dcd42e9812c9a174938dbafe067d47b8e3e2c0fcb6a7`。该早期 smoke 未重新生成，未应用后续新增的末尾答案题号回链功能；重编译核对的是其原版本。

正式 CH01 已完成自动流程：5/5节、11页、37次累计真实请求，状态 `AWAITING_USER_REVIEW`。content/compile/layout/security PASS，math/policy NEEDS_REVIEW；教师验收 NOT_RUN。部分定性证明没有可执行符号核算，不能把自动编译通过写成数学全面通过。CH02/CH03分别保留在33/27请求的预算阻塞状态，等待明确增额选择；失败草稿和日志保留。

| 案例 | PDF | 主 TeX | 完整源码 ZIP | 独立新目录重编译 |
|---|---|---|---|---|
| CH01 数列与数列极限 | [PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/vbfde334fb51c/build/lecture.pdf>) | [lecture.tex](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/vbfde334fb51c/source/lecture.tex>) | [source_bundle.zip](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/05748ab6260c4098/vbfde334fb51c/source_bundle.zip>) | [PASS：11页及逐页文字/链接数一致](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/live-zip-recompile-20260920-043108.json>) |

CH01 PDF SHA-256：`387b65fa187488b44e94bc468cb82a956c256cf224a29e636c343f1e7c945b0b`；ZIP：`87e9be7fb24e3637dabffa1fd5ffb511e89e7ccd4fd4c313f5906ee15bf44993`。独立重编译调用API为0；实际原讲义9页仅作结构参照，11页不是优劣评分。

## 已保存的部分讲义（PARTIAL）

以下是截至成功检查点的累计预览，后续小节尚未通过或尚未生成。两个任务仍为BLOCKED，不能当作完整讲义或教师验收通过。CH02已有求和下标与文字不一致的问题待修；具体比较见[三章逐项对照](THREE_CHAPTER_COMPARISON.md)。

|案例|范围|PDF|TeX|状态|
|---|---|---|---|---|
|CH02|截至S03，累计10页|[部分PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/fd6736af6ef14be3/sS03_4728b49f0563/build/lecture.pdf>)|[部分TeX](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/fd6736af6ef14be3/sS03_4728b49f0563/source/lecture.tex>)|PARTIAL / 教师NOT_RUN|
|CH03|截至S02，累计6页|[部分PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/sS02_f4c6b3226390/build/lecture.pdf>)|[部分TeX](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/a45be503af594ce8/sS02_f4c6b3226390/source/lecture.tex>)|PARTIAL / 教师NOT_RUN|

[逐文件SHA与检查点证据](partial-deliverables-final.json)。这些链接保持原检查点文件，未改正文或清除失败记录；界面还可下载每个已保存小节的TeX/PDF/检查点。

## 三章双模板课件

六组均由真实三章讲义转换，使用完整原稿中可追溯的书目补充；原资料与既有 case 文件未覆盖。全部六组原构建的 Windows XeLaTeX 与来源核验已 PASS，共 522 个物理页已渲染，自动几何仍 NEEDS_REVIEW。以下都是待教师复核的草稿。

ZIP 来自各组实际 `case/source`，包含主 TeX、实际主题/字体/风格适配与所需图片，以及 README、MAIN_FILE。编译与来源清单、逐文件 SHA-256 随 ZIP 旁置提供，JSON 不进入 ZIP，保留应用上传兼容性。请优先下载 v2 ZIP；单独主 TeX 可能缺少相邻依赖。所有链接为本机绝对路径。

| 章节 / 模板 | PDF | 主 TeX | 完整源码 ZIP | 清单 / SHA | 页数 | 新目录重编译 |
|---|---|---|---|---|---:|---|
| CH01-default | [PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-013122-adaptive-v2-default/CH01-default/build/slides.pdf>) | [slides.tex](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-013122-adaptive-v2-default/CH01-default/source/slides.tex>) | [source_bundle-v2.zip](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH01-default/source_bundle-v2.zip>) | [compile_manifest](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH01-default/compile_manifest.json>) / [SHA-256](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH01-default/FILE_SHA256.json>) | 77 | PASS |
| CH01-fduclassroom | [PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-012826-adaptive-v2/CH01-fduclassroom/build/slides.pdf>) | [slides.tex](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-012826-adaptive-v2/CH01-fduclassroom/source/slides.tex>) | [source_bundle-v2.zip](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH01-fduclassroom/source_bundle-v2.zip>) | [compile_manifest](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH01-fduclassroom/compile_manifest.json>) / [SHA-256](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH01-fduclassroom/FILE_SHA256.json>) | 77 | NOT_RUN |
| CH02-default | [PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-013122-adaptive-v2-default/CH02-default/build/slides.pdf>) | [slides.tex](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-013122-adaptive-v2-default/CH02-default/source/slides.tex>) | [source_bundle-v2.zip](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH02-default/source_bundle-v2.zip>) | [compile_manifest](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH02-default/compile_manifest.json>) / [SHA-256](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH02-default/FILE_SHA256.json>) | 76 | NOT_RUN |
| CH02-fduclassroom | [PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-012826-adaptive-v2/CH02-fduclassroom/build/slides.pdf>) | [slides.tex](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-012826-adaptive-v2/CH02-fduclassroom/source/slides.tex>) | [source_bundle-v2.zip](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH02-fduclassroom/source_bundle-v2.zip>) | [compile_manifest](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH02-fduclassroom/compile_manifest.json>) / [SHA-256](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH02-fduclassroom/FILE_SHA256.json>) | 76 | NOT_RUN |
| CH03-default | [PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-013122-adaptive-v2-default/CH03-default/build/slides.pdf>) | [slides.tex](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-013122-adaptive-v2-default/CH03-default/source/slides.tex>) | [source_bundle-v2.zip](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH03-default/source_bundle-v2.zip>) | [compile_manifest](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH03-default/compile_manifest.json>) / [SHA-256](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH03-default/FILE_SHA256.json>) | 108 | NOT_RUN |
| CH03-fduclassroom | [PDF](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-012826-adaptive-v2/CH03-fduclassroom/build/slides.pdf>) | [slides.tex](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-beamer/20260920-012826-adaptive-v2/CH03-fduclassroom/source/slides.tex>) | [source_bundle-v2.zip](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH03-fduclassroom/source_bundle-v2.zip>) | [compile_manifest](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH03-fduclassroom/compile_manifest.json>) / [SHA-256](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/CH03-fduclassroom/FILE_SHA256.json>) | 108 | PASS |

所有六份 ZIP 的成员、CRC 与 SHA-256 均已核对；原 source 与已编译 PDF 哈希保持一致。CH01/default 与 CH03/FDU 通过应用实际 safe_extract_zip 解压，在全新目录使用真实 XeLaTeX 重新编译，检查实际页数和全部页面提取文字是否与基线一致。其它四份未再次重编译，其原 case 编译 PASS 与 ZIP 逐文件哈希一致为本次证据边界。复编译未再次渲染全部页面，原六组全页 PNG 已保留。

[交付及重编译机器记录](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/delivery-20260920-020236.json>)。其中包含每个 ZIP 的哈希、全部成员哈希和独立编译结果/日志路径；失败也原样保留。

首版 ZIP 将 JSON 清单放在包内，曾被应用上传白名单拒绝，尚未进入编译；[首次失败记录](<D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-delivery/delivery-20260920-015918.json>) 已保留。随后首版按已校验成员独立解压的两份重编译通过，但不作为上传兼容性证据。最终 v2 把 JSON 旁置，重新使用应用解压器及实际编译验证；首版 ZIP、两轮旧日志和旧目录全部保留，不覆盖或删除。

相关证据：[三章双模板比较](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/beamer_comparison.md>)；[完整原稿来源审计](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/source_audit.md>)；[界面与书目回归](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/ui_validation.md>)；[第二轮验收草稿](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/acceptance_template.md>)。

教师数学/逐页视觉验收：NOT_RUN。本次打包/复编译的真实 API 调用：0。原生 trusted_local 不是隔离沙箱。FDU 私人主题与图片的公开再分发许可未认定。真实模型生成讲义在上方另列，不将课件转换测试当作模型教学生成通过。
