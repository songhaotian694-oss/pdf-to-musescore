# 错误后的自动对照校正

默认转换发现 `editable_draft_needs_correction` 后，不立即结束任务。先读取 `correction-worklist.json`，最多执行两轮校正：

1. 打开工作单列出的源 PDF 页缩略图和校对谱页；定位声部、小节索引和错误类型。
2. 在 `score.mscz` 的新副本中修改，命名为 `score-correction-01.mscz`、`score-correction-02.mscz`；不得覆盖初始草稿、原始 MXL 或 OMR。
3. 谱表、系统、小节线、谱号或节奏分割错误优先修正 `.omr`，重新导出 MusicXML；播放音色和断点使用现有专用脚本修复。
4. 只有 PDF 图像清晰、目标符号和位置唯一时，才自动修改音高、时值、附点、临时记号、连线或休止。每项修改记录源页、声部、小节、修改前后和视觉依据。
5. 每轮重新导出校对 PDF、MusicXML 和 MIDI，运行内容、基准、播放与布局验证。只保留错误减少且没有新增门禁错误的副本。
6. 两轮后仍有歧义时停止自动修改，交付问题较少的可编辑草稿和剩余工作单；不向用户声称已经修好。

可以自动完成且风险较低的项目包括：选择更好的 OMR 候选、明确的播放音色、已配置的布局断点、与已校正 MSCZ 完全匹配前提下的编号复核。不能从 PDF 唯一确定的缺失发声音符、复调归属、跨页连线和模糊临时记号必须保留为人工项。

`correction-worklist.json` 将验证错误去重并分类为 `reference_timeline`、`rhythm_structure`、`staff_structure`、`text_recognition`、`playback`、`layout` 或 `notation`，附带源页、校对页、声部和可解析的小节索引。

修正副本可直接重新验收；省略 `-ProofPdfPath` 时会自动从该 MSCZ 生成新的校对 PDF：

```powershell
& '<skill>/scripts/verify-output.ps1' -RunDirectory '<run>' -ScorePath '<run>/score-correction-01.mscz' -OutputMode draft
```

验证结果中的 `verifiedScore` 和 `proofPdf` 必须指向本轮副本及其新校对谱。下一轮只能以错误数量减少、且没有新增错误的版本为基础。


