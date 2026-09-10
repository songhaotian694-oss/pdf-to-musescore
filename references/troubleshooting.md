# 故障排查与恢复

v2 首次 `needs_selection` 是正常预检停点，OMR 尚未运行。读取全部源页缩略图，按 `page-selection.md` 建立经过核对的计划后，带 `-SelectionPlan` 与 `-GroupId` 重跑。

`failed_content_validation` 不能仅凭 MSCZ 可打开就交付。查看逐声部小节数、谱号、歌词和全部校对页。只根据源谱纠正预期，不照抄错误输出绕过检查。近空白页修复后需要重新验证。

下面的旧版恢复流程仅适用于确定未混合页面的候选。v2 的 `run.json` 还必须有 `schemaVersion:2` 和 `selection`（经核对的 `selection.json` 绝对路径）；缺少它不通过内容检查。混合输入的旧 MXL 不要直接复用，应按选定页组重新识谱。

- `Audiveris is missing`：安装官方 Windows 包，指定 `-AudiverisPath`，用 `-help` 验证；不要把 PDF 直接作为 MuseScore 输入。
- 无 MXL/无音符：检查 `audiveris.stdout.log` 和 `audiveris.stderr.log`，确认输入是清晰印刷五线谱。普通文字 PDF 不能转为音符。可视化查看源 PDF 后决定是否提高扫描质量。
- Audiveris 超时/非零：保留 OMR 和日志，查看失败页；按实际原因修复后用新目录重试，不将残留文件当作成功。
- 缺 MuseScore：`audiveris` 子目录中的 MusicXML 保留。安装后，按下述流程继续。
- 导出失败：检查该步骤的 stdout/stderr 日志、可写目录和磁盘空间；不要覆盖输入或关闭用户已打开的 MuseScore 进程。
- 缺 `pdfinfo`：使用 Poppler 或 Codex 提供的 Poppler，将绝对路径写入 `config.local.json` 的 `PdfInfo` 或传 `-PdfInfoPath`。不要以 PDF 文本正则猜测可靠页数。
- 多候选：报告退出码 2。先列出所有候选和源页对照，请用户确定乐章；每个选定候选各建一个新的目录。

## 从保留的 MusicXML 恢复

读取 `scripts/common.ps1` 后，用 `Find-ScoreTool` 探测路径，用 `Invoke-ScoreProcess` 逐步执行导出并检查退出码。每个用户选定的候选都创建唯一的新输出目录，保留原候选，复制到新目录为 `source.mxl` 或 `source.musicxml`，从复制前记录 `startedUtc`。写入 `run.json`：

```json
{"startedUtc":"<本次恢复开始的 UTC ISO8601 时间>","inputPdf":"<原PDF绝对路径>","musicXml":"<本次新目录复制后的MusicXML绝对路径>","exportMidi":false}
```

按 MuseScore 参考依次生成 `score.mscz`、`score-proof.pdf`、可选 `score.mid`，调用 `verify-output.ps1 -RunDirectory <新目录>`，写回 `report.json` 和 `report.md`（可用 `Write-ScoreReport`）。记录来源候选和用户选择，不修改原运行的失败报告。验证失败仍报告失败。
