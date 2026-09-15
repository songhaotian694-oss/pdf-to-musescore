# 草稿与严格验收模式

转换脚本提供两种输出模式，分别用于“先得到可编辑谱，再逐步校正”和“只接收通过门禁的结果”。

## `draft`：默认生成可编辑草稿

使用 `-OutputMode draft`，也可以省略该参数。Audiveris 只要生成了可解析的 MusicXML，MuseScore 就继续导入并尝试输出：

- `score.mscz`：可编辑草稿；
- `score-proof.pdf`：用于逐页对照；
- 原始 MusicXML、OMR 工程、日志和各项验证报告；
- 使用 `-ExportMidi` 时另有 `score.mid`。

声部数、小节数、休止区间、谱号或歌词不一致不会阻止 MSCZ 生成。播放音色设置失败时保留 MuseScore 导入后的播放配置；布局处理失败时保留上一阶段的布局。报告状态为 `editable_draft_needs_correction` 或 `editable_draft_ready_for_review`，退出码为 0，`acceptancePassed` 始终为 false。

草稿模式仍然运行所有能执行的检查并保留错误，不把失败降级成“通过”。无法获得可解析 MusicXML、MuseScore 无法导入／保存／重新打开、输出为空或缺少必需工具等技术错误仍停止，因为这些情况下没有可靠的可编辑文件。

## `validated`：严格验收

需要交付或演奏前的严格结果时显式使用：

```powershell
scripts/convert-score.ps1 ... -OutputMode validated
```

内容、播放或布局门禁失败时分别退出 3、4、5；只有所有已配置检查通过才返回 `completed_needs_manual_review`，并将 `acceptancePassed` 设为 true。即使通过，仍需人工逐页校对和试听。

推荐流程是先用默认草稿模式取得 MSCZ，在副本中根据源 PDF 修正，再对修正后的新运行使用严格模式或重新执行验证。不要修改预期值迎合错误 OMR，也不要把 `editable_draft_*` 状态描述为成品或验收通过。

