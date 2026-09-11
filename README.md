# PDF to MuseScore Skill

将清晰印刷五线谱 PDF 转成可编辑 MuseScore 工程的本地 Skill。使用 Audiveris 识谱、MuseScore Studio 导入和导出；包含页组核对、结构检查、播放音色设置、换行分页处理和回归测试。

## 环境与安装

当前面向 Windows PowerShell 和 Python 3。本地验证使用 Audiveris 5.11.0、MuseScore Studio 4.7.3；其他版本需重新验证。应用程序、OCR 语言模型和音色库不随仓库分发，请分别安装。

1. 将仓库内容放到个人 Skill 目录中的 `pdf-to-musescore` 文件夹。
2. 安装 Audiveris、MuseScore Studio、Poppler，以及 Python 依赖：`python -m pip install -r requirements.txt`。
3. 将 `config.example.json` 复制为 `config.local.json`，按本机实际安装路径填写。配置文件已被 Git 忽略；示例路径不能直接使用。Audiveris 文字识别需其兼容的 Tesseract 语言数据。
4. 阅读 [SKILL.md](SKILL.md)，运行 `scripts/detect-dependencies.ps1` 检查依赖。

## 转换流程

首次调用 `scripts/convert-score.ps1 -InputPdf <PDF绝对路径> -OutputDirectory <输出父目录绝对路径>`，生成全页缩略图和预检报告。助手核对全部源页，按 [页组计划](references/page-selection.md) 准备选择计划；总谱和独立分谱不能串接。

随后传入 `-SelectionPlan <计划绝对路径> -GroupId <组名>` 执行转换。`-ExportMidi` 可选，音色验证始终执行。默认 `-LayoutMode reflow` 清理导入副本的硬换行／分页；要求保留源断点时选 `source`。

每次创建新输出目录，保留原件及中间结果。输出包括 MSCZ、校对 PDF、可选 MIDI、原始 MusicXML 与验证报告。

## 边界

通过自动检查不等于音符准确或排版完善，仍需逐页核对和试听。当前播放映射支持 violin、viola、cello、piano、trombone、baritone-horn、euphonium；复杂换乐器、拨弦、铜管弱音器等需要进一步验证。详见 [播放](references/playback.md)、[布局](references/layout.md) 和 [人工清单](references/correction-checklist.md)。

## 测试

在仓库根目录运行：

```powershell
python tests/test-structure.py
python tests/test-playback.py
python tests/test-layout.py
```

当前共 34 项单元测试。真实应用集成测试需要另行生成原创测试谱并安装上述依赖；见 [tests](tests/README.md)。仓库不包含用户乐谱、本机配置、应用安装包或历史转换输出。
