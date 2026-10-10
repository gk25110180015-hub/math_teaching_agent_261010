# CH02-fduclassroom 可编辑课件源包

主文件：slides.tex。这些文件来自已经编译的 Beamer case/source 目录，不是原讲义或 prepared-input 副本。
在解压目录用 XeLaTeX 连续编译至少两遍：

    xelatex -no-shell-escape -interaction=nonstopmode -halt-on-error slides.tex
    xelatex -no-shell-escape -interaction=nonstopmode -halt-on-error slides.tex

本机验证环境为 Windows 11 / TeX Live 2024。需要 ctexbeamer、Fandol 与源码所用 TeX 宏包；系统字体和 TeX 发行版不包含在 ZIP 内。FDU 包包含实际主题 sty 和 resources/fudan.pdf；其它工作流字体与风格适配均已包含。无需模型密钥或网络 API。

原始参考资料保持不变。补入书目只从完整原稿复制，provenance 见与 ZIP 并列交付的 compile_manifest.json。原构建全部物理页已渲染；教师数学与逐页视觉审核仍 NOT_RUN，这份源包是待复核草稿。字体替换等 review 提示见清单，不把编译成功当作教学验收。

旁置 FILE_SHA256.json 包含全部 ZIP 成员与旁置编译清单的 SHA-256；它不包含自身哈希。源包及全部成员哈希另记录于工程 delivery 证据。JSON 元数据留在 ZIP 外，ZIP 可按应用原上传规则重新导入。用户资料、FDU 主题与图片只作本机私人交付，未认定公开再分发许可。
