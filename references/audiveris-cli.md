# Audiveris CLI

官方来源：https://github.com/Audiveris/audiveris/releases

CLI 文档：https://audiveris.github.io/audiveris/_pages/guides/advanced/cli/

本机构建时用 Audiveris 5.11.0 Windows Console 版 `-help` 验证：

```powershell
& $audiveris -batch -transcribe -export -save -output $omrDirectory -- $inputPdf
```

`-save` 在批量流程中保存 OMR；`-export` 导出 MusicXML。`--` 后面是输入路径。为多个乐章生成的多个输出不能任意取第一个。仅从当前新建输出目录收集 MXL/MusicXML。CLI 返回 0 仍需检查是否有可解析、含音符/休止符的 MusicXML。

本机使用官方 MSI 行政解包布局，包含 `runtime`，无需另装 Java。脚本对 Audiveris 子进程设置运行目录下的 APPDATA/LOCALAPPDATA/TEMP/TMP，隔离日志、缓存与分类器临时文件；不改变系统或用户环境变量。本机配有约 23 MiB 的官方英文 OCR 数据 `eng.traineddata`，来源 https://github.com/tesseract-ocr/tessdata 。路径通过 `config.local.json` 的 `Tessdata` 或 `-TessdataDirectory` 配置，子进程设置 `TESSDATA_PREFIX`。本版本调用 legacy OCR，不能使用仅含 LSTM 的 tessdata_fast 数据，否则标题和歌词会丢失。非英文歌词需另行安装对应语言并验证 Audiveris 语言配置。

更换版本后重新执行 `-help`、`-version` 和最小 PDF 测试。路径由探测或显式参数提供，不把此文档中的版本当作固定依赖。
