# 已校正 MSCZ 编号基准

只有用户明确指定某个 MSCZ 已经校正、并要求把它作为同一曲目的结构与编号基准时，才使用：

```powershell
scripts/convert-score.ps1 ... -ReferenceMscz <已校正MSCZ绝对路径>
```

脚本先让 MuseScore 从基准 MSCZ 导出 MusicXML，再生成 `reference-baseline.json`。基准记录：

- 每个声部的实际小节序列；
- 每小节时值和整小节静默状态；
- MusicXML 小节编号；
- 基准谱面每个系统起点对应的小节编号；
- 基准 MSCZ 与导出 MusicXML 的 SHA-256。

原始和灰度 OMR 候选都会与基准时间线比较，差异计入 `qualityPenalty`。最终 MSCZ 重新打开并导出 MusicXML 后再次检查，结果写入 `measureNumberValidation`。草稿模式保留差异并继续输出；严格模式按内容错误退出 3。

这里的“编号基准”不表示可以只修改屏幕上显示的小节号。实际小节数量、时值或休止不一致时，必须先人工修正音乐结构，再重新验证。脚本不会根据基准复制音符、自动补删小节或伪造休止。

未提供 `-ReferenceMscz` 时，该项明确报告 `not_checked`。普通参考文件、未经校正的 MSCZ 或来源不明的工程不能自动视为权威。
