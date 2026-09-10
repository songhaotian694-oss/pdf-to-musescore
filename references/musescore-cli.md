# MuseScore CLI

本机 `MuseScore4.exe --help` 已确认 `-o/--export-to`，扩展名决定格式。构建验收采用本机 Studio 4.7.3。

```powershell
& $musescore -o $outputMscz $inputMxl
& $musescore -o $proofPdf $outputMscz
& $musescore -o $outputMidi $outputMscz
& $musescore -o $verifyMusicXml $outputMscz
```

最后一步再次读取 MSCZ 并导出 MusicXML，验证可重新打开。所有输出用全新路径，捕获 stdout、stderr 和退出码。导出失败保留识别结果，不用 `-f` 掩盖损坏警告。默认不打开交互窗口；只有用户要求打开或指定 `-OpenInMuseScore` 时才打开 GUI。

这些是格式导出命令，不是完整验收流程。导入 MSCZ 后必须先执行 [音色分配](playback.md)，用 MuseScore 重新保存修正副本，再导出并解析 MIDI。转换脚本已集成该流程；恢复旧任务时也不能跳过。

MuseScore 根据 MusicXML 重新排版，校对 PDF 页数不一定等于源 PDF。不能仅靠页数一致判定识别完整。
