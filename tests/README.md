# 验收测试

## v2 回归

`test-structure.py` 包含 11 项确定性规则测试：逐声部小节、错误谱号、允许的正常谱号变化、器乐误歌词、未知预期披露、重复页、错误哈希／未复核计划、5 个混合页组及空白图像。

`create-mixed-fixture.py <绝对目录>` 创建原创 28 小节四重奏和四个分谱 MusicXML。用 MuseScore 各自导出 PDF，再用 pypdf 按总谱 4 页＋四个分谱各 1 页合为 8 页。首次 `convert-score.ps1` 不带计划应退出 2，生成 5 组草案和全部缩略图，且不存在 `audiveris/`。逐页复核后，为测试场景编写已选择总谱／分谱的计划，分别实跑 OMR：总谱期望每声部 28 小节；分谱期望 1 声部、28 小节、正确谱号，均无歌词。保留未通过的真实 OMR 结果，它们是结构检查的负例，不得更改预期凑通过。

`run-content-regression.py --run <成功总谱运行目录> --out <全新测试目录> --powershell <pwsh.exe绝对路径>` 在成功结果的副本中注入多余小节、错误大提琴谱号、页脚误歌词和校对空白页，4 项都应返回退出码 3。空白页测试特别要求 `technicalValidation=passed` 与 `failed_content_validation` 同时出现。原运行保持不变；这些是故障注入测试，不是音符准确率测试。

旧 `run-tests.ps1` 已适配 v2：对原创正常夹具生成已知结构计划；普通文字 PDF 改为预检退出 2、不启动 OMR。修正单页 PowerShell 数组序列化后可用 `-TestName` 重跑特定项。大型测试输出不包含在仓库中；请在本机生成原创夹具并运行验证。

## 原有夹具和验证

测试构建器 `create-fixtures.py` 生成原创机械练习音型的 MusicXML，再由本机 MuseScore 生成印刷 PDF；测试使用生成的 PDF 作为 Audiveris 输入，绝不把 fixture MusicXML 伪装成 OMR 输出。

运行 `run-tests.ps1`，传入本机 `-MuseScorePath`、`-PdfInfoPath`。一页单旋律、两页钢琴谱、歌词/多声部、中文空格路径、已有目录不覆盖、缺 Audiveris、缺 MuseScore、无效 PDF 和文字 PDF 都纳入验收。真实 OMR 测试可能耗时数分钟。

每次测试结果保存到构建目录的 `test-results.json`，含命令参数、退出码、输出文件大小、验证结果和人工检查项。fixture、源 PDF、运行日志、报告一同保留。测试通过只证明转换流程和失败行为，不证明识别音符准确；比较源谱和校对谱查看 OMR 限制。

另执行 skill-creator 的 `quick_validate.py` 和 PowerShell 语法检查。安装后需要在下一次对话确认 `$pdf-to-musescore` 出现在可用技能中；元数据校验不能替代真正的新回合发现测试。
# Playback regression

Brass: `run-brass-smoke.py --musescore <absolute MuseScore4.exe> --out <new absolute directory>` tests real import/resave/MIDI for trombone, baritone-horn, euphonium and a B-flat transposing part. The playback unit suite now has 18 cases; the full unit total is 34. MIDI note pitches/ticks must remain unchanged after instrument assignment.

Layout: run `python tests/test-layout.py` to verify physical break removal, section/nobreak preservation, source mode, no overwrite and rejection of reintroduced breaks. Real MuseScore tests must resave both reflow and source modes, check `layoutValidation`, and inspect every proof page; fewer pages alone is not success.

Run `python tests/test-playback.py`: 18 independent SMF/MSCZ cases cover quartet programs, trombone/baritone-horn/euphonium programs and transposition preservation, default piano, swapped instruments, missing or late program changes, bank, percussion/shared channels, track order, running status, original preservation, unknown names, overwrite refusal, two-staff piano and truncated MIDI. Use the configured Python executable and absolute script path.

Real MuseScore acceptance must import, assign, resave and export MIDI. Quartet expects raw programs 40/40/41/42; a single cello expects 42. Test without `-ExportMidi` too: verification must still generate a MIDI. Original generic melody regression fixtures explicitly request piano; they do not imply every unknown source instrument is piano.
