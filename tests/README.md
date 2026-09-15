# 验收测试

## v2 回归

`test-structure.py` 包含 15 项确定性规则测试：逐声部小节、错误谱号、允许的正常谱号变化、器乐误歌词、未知预期披露、重复页、错误哈希／未复核计划、5 个混合页组、空白图像、候选罚分、灰度 PDF 页数／不覆盖，以及 MSCZ 基准时间线一致和时值／休止／编号差异。

`create-mixed-fixture.py <绝对目录>` 创建原创 28 小节四重奏和四个分谱 MusicXML。用 MuseScore 各自导出 PDF，再用 pypdf 按总谱 4 页＋四个分谱各 1 页合为 8 页。首次 `convert-score.ps1` 不带计划应退出 2，生成 5 组草案和全部缩略图，且不存在 `audiveris/`。逐页复核后，为测试场景编写已选择总谱／分谱的计划，分别实跑 OMR：总谱期望每声部 28 小节；分谱期望 1 声部、28 小节、正确谱号，均无歌词。保留未通过的真实 OMR 结果，它们是结构检查的负例，不得更改预期凑通过。

`run-content-regression.py --run <成功总谱运行目录> --out <全新测试目录> --powershell <pwsh.exe绝对路径>` 在成功结果的副本中注入多余小节、错误大提琴谱号、页脚误歌词和校对空白页，4 项都应返回退出码 3。空白页测试特别要求 `technicalValidation=passed` 与 `failed_content_validation` 同时出现。原运行保持不变；这些是故障注入测试，不是音符准确率测试。

旧 `run-tests.ps1` 已适配 v2：对原创正常夹具生成已知结构计划；普通文字 PDF 改为预检退出 2、不启动 OMR。修正单页 PowerShell 数组序列化后可用 `-TestName` 重跑特定项。详细 v2 证据保存在构建工作区 `D:\app\skill\build-v2`，不随技能复制大型测试输出。

## 原有夹具和验证

测试构建器 `create-fixtures.py` 生成原创机械练习音型的 MusicXML，再由本机 MuseScore 生成印刷 PDF；测试使用生成的 PDF 作为 Audiveris 输入，绝不把 fixture MusicXML 伪装成 OMR 输出。

运行 `run-tests.ps1`，传入本机 `-MuseScorePath`、`-PdfInfoPath`。一页单旋律、两页钢琴谱、歌词/多声部、中文空格路径、已有目录不覆盖、缺 Audiveris、缺 MuseScore、无效 PDF 和文字 PDF 都纳入验收。真实 OMR 测试可能耗时数分钟。

每次测试结果保存到构建目录的 `test-results.json`，含命令参数、退出码、输出文件大小、验证结果和人工检查项。fixture、源 PDF、运行日志、报告一同保留。测试通过只证明转换流程和失败行为，不证明识别音符准确；比较源谱和校对谱查看 OMR 限制。

另执行 skill-creator 的 `quick_validate.py` 和 PowerShell 语法检查。安装后需要在下一次对话确认 `$pdf-to-musescore` 出现在可用技能中；元数据校验不能替代真正的新回合发现测试。

## 输出模式回归

`run-selfcheck.py` 同时验证 `validated` 与 `draft`。删除最终小节或删除布局报告时，严格模式仍分别返回 3／5；草稿模式必须返回 0、`technicalValidation=passed`、`acceptancePassed=false` 和 `draft_with_validation_issues`，并保留具体错误。正常严格结果仍为 `passed`。
# Playback regression

Brass: `run-brass-smoke.py --musescore <absolute MuseScore4.exe> --out <new absolute directory>` tests real import/resave/MIDI for trombone, baritone-horn, euphonium and a B-flat transposing part. The playback unit suite has 23 cases; the full unit total is 59. MIDI note pitches/ticks must remain unchanged after instrument assignment.

Layout: run `python tests/test-layout.py` to verify physical break removal, section/nobreak preservation, source mode, no overwrite and rejection of reintroduced breaks. Real MuseScore tests must resave both reflow and source modes, check `layoutValidation`, and inspect every proof page; fewer pages alone is not success.

Run `python tests/test-playback.py`: 23 independent SMF/MSCZ cases cover silent parts/staves, missing sounding tracks, brass and quartet programs, default piano, swapped instruments, missing or late program changes, bank, percussion/shared channels, track order, running status, original preservation, unknown names, overwrite refusal, two-staff piano and truncated MIDI. Use the configured Python executable and absolute script path.

Real MuseScore acceptance must import, assign, resave and export MIDI. Quartet expects raw programs 40/40/41/42; a single cello expects 42. Test without `-ExportMidi` too: verification must still generate a MIDI. Original generic melody regression fixtures explicitly request piano; they do not imply every unknown source instrument is piano.

## 休止回归

`python tests/test-rests.py` 包含 16 项原创夹具测试：小节漏空、只有 forward／倚音、3/4 与 12/8 整小节休止、拍号和 divisions 继承、加法拍号、整小节休止时值或起点错误、跨谱表 backup、8 小节休止已展开不重复计数、多加隐藏休止、26 小节被压成 4 小节、未展开的多小节休止、未知源预期及错误计划。使用实际序号定位，显示小节号不能绕过检查。

`test-playback.py` 另覆盖整段休止的中间声部、钢琴单手休止、全休止谱、缺失发声轨道和缺失谱表不能当成休止。

真实 MuseScore 验收应使用原创 8 小节和 26 小节休止夹具，以及中间声部全休止／全谱休止夹具；导入、设置音色、重新保存，再导出 MusicXML 和 MIDI。检查休止区间、首次 Note On 位置及无音符声部的报告，不用程序号正确替代时间轴检查。用户提供的问题乐谱仅在本地诊断，不纳入仓库。
