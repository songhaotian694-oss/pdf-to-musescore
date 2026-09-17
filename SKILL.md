---
name: pdf-to-musescore
description: Convert printed sheet-music PDFs into editable MuseScore scores using Audiveris OMR and MuseScore Studio. Use when the user asks to recognize, transcribe, import, or convert a PDF score into MSCZ, MusicXML, MIDI, or an editable MuseScore project.
---

# PDF 乐谱转 MuseScore

处理用户提供或授权访问的清晰印刷五线谱。先确认页面属于哪份乐谱，再识谱；一个 PDF 或一个 MXL 不等于一份连续乐谱。文件能打开不等于内容可用，不宣称已测得音符准确率。

## 转换前：全页核对与选组

1. 运行 `scripts/detect-dependencies.ps1` 检查 Audiveris、MuseScore、Poppler 和可写目录。Python 另需 `pypdf`、`pypdfium2`、`numpy`、`Pillow`，配置到 `config.local.json` 的 `Python`。安装前说明官方来源、位置和大小，不重复安装，不修改系统 PATH。
2. 首次运行 `scripts/convert-score.ps1 -InputPdf <绝对路径> -OutputDirectory <绝对父目录>`，生成 `preflight.json` 和全部源页缩略图，返回退出码 2 / `needs_selection`。**此时未运行 OMR**。
3. 检查**每一页**缩略图：系统与谱表、标题／乐器、谱号、小节编号是否重新开始、页眉页脚和歌词位置。自动分组只是草案；扫描 PDF 可能没有文本，谱表启发式也可能不准，必须视觉复核。
4. 用户已指定总谱、分谱或页码时按既有选择继续；单份明确连续乐谱可自行核对后继续，不必再问。多个独立页组且用户未选范围时，展示页组并询问需要总谱、哪些分谱或全部分别生成。不得串接独立分谱。
5. 按 [页组计划格式](references/page-selection.md) 写入 JSON：源哈希、已检查的全部页、各组预期声部数／歌词／小节数／允许谱号。记录源谱中可确认的信息，不能根据 OMR 输出反推预期以绕过检查。未知小节数和谱号用 null，披露未执行对应检查。
6. 仅当用户明确指定某个同曲目 MSCZ 已经校正并作为基准时，传入 `-ReferenceMscz <绝对路径>`。脚本从它提取实际小节、时值、休止和系统起点编号，候选和最终结果都必须与其比较。详见 [已校正 MSCZ 基准](references/reference-mscz.md)。

## 分组转换

运行 `scripts/convert-score.ps1 -InputPdf <源PDF> -OutputDirectory <父目录> -SelectionPlan <已核对JSON> -GroupId full-score`。默认 `-RecognitionProfile auto`：先识别原始 PDF，结构检查失败时自动尝试 400 DPI 灰度输入，并按已复核结构选择问题更少的候选；若提供已校正 MSCZ 基准，其时间线差异也计入候选选择。无需让用户理解或选择 Audiveris 参数。详见 [自动提高识别质量](references/recognition-quality.md)。

默认 `-OutputMode draft`：有内容、播放或布局疑点时继续生成明确标记的可编辑草稿；技术上无法生成／重开文件时才停止。需要门禁全部通过后才输出时使用 `-OutputMode validated`。两种模式、状态和退出码见 [草稿与严格验收](references/output-modes.md)。

草稿出现错误后不要立即交付。读取自动生成的 `correction-worklist.json`，主动打开其中的源 PDF 页和校对谱页，在新 MSCZ／OMR 副本上最多进行两轮有视觉证据的修正，每轮重新导出并运行全部验证。明确可见的错误直接修正，不要求用户理解技术细节；图像含糊或不能唯一确定的音乐内容不得猜测。完整规则见 [错误后的自动对照校正](references/auto-correction.md)。

`-ExportMidi` 可选；`-OpenInMuseScore` 仅在用户要求打开时使用。选择全部时逐组调用，建议输出父目录按组名区分。

脚本拆出选定页组，再执行 Audiveris → MXL → MSCZ → 校对 PDF。自动识别回退会在处理期间保留原始和灰度两次 OMR、MXL、日志与罚分，不能把候选选择描述为音符准确率测量。`selection.json` 和 `run.json` 保留原 PDF 哈希、页码与分组。转换成功且无需继续自动校正时，默认清除缩略图、临时 PDF、Audiveris 工程／缓存、验证副本、过程 MSCZ 和 stdout／stderr 日志；保留最终 MSCZ、校对 PDF、可选 MIDI、选中的 MusicXML/MXL、报告、选择计划与校正工作单。失败、`needs_selection` 或 `editable_draft_needs_correction` 必须保留中间文件用于诊断和修正；显式传入 `-KeepIntermediate $true` 也保留全部中间文件。每次仍创建新目录，不覆盖，`-Force` 不绕过分组或验证。路径全部绝对化，以参数数组传递。

CLI 与恢复说明见 [Audiveris](references/audiveris-cli.md)、[MuseScore](references/musescore-cli.md)、[排查指南](references/troubleshooting.md)。多个 MXL 仍返回 `needs_selection`，列出全部候选，不默默取第一个。

## 验证和交付

源谱有整小节／多小节休止时，按 [休止与进入位置](references/rests.md) 从源谱记录 `expectedRestSpansPerPart`，核对休止数量、当前拍号和休止后的进入小节。多小节休止不能压成一个实际小节，已经展开的休止也不能重复添加；不能靠改小节号或隐藏休止修复时长。

铜管已支持长号 `trombone`、次中音号 `baritone-horn`，并分别支持源谱标为 Euphonium 的 `euphonium`。按 [播放说明](references/playback.md) 区分乐器及记谱移调；修复音色不会自动移调音符。

排版默认使用 `-LayoutMode reflow`：仅清理导入副本的硬换行、硬分页，让 MuseScore 自动排版，保留乐章分隔。用户需要保留源断点时用 `-LayoutMode source`。规则与校对要点见 [换行和分页](references/layout.md)，不把减少页数当成质量目标。

导入后必须执行 [播放音色设置和 MIDI 核验](references/playback.md)。弦乐四重奏按源谱顺序设置 Violin、Violin、Viola、Cello，原始 MIDI 程序号为 40、40、41、42（GM 从 1 起显示为 41、41、42、43）。在页组计划中明确 `playbackInstruments`，不要把谱表名称当成音色已正确的证据。

## 小节编号：禁止显示补偿

最终 MSCZ 不得写入或保留任何用于补偿显示编号的机制，包括：

- `<noOffset>` 的非零值；
- 手工 `<MeasureNumber>` 文字覆盖；
- 用 `measureNumberMode` 或隐藏小节号掩盖结构错误。

发现上述内容时，`measureNumberValidation` 必须失败，状态为 `numbering_compensation_detected`。不得通过增加、修改或保留编号偏移来使行首编号“看起来正确”。

禁止用小节编号偏移修复 OMR 错误。若编号漂移，定位第一个漂移点，比较其前后实际小节、时值及多小节休止展开；只修复该处的实体结构。无法唯一判断时，保留为待人工校对草稿，不交付“编号已修正”的 MSCZ。

- `technicalValidation`：文件非空、新生成、MXL/XML 有效、MSCZ 再次读取、PDF 页数、可选 MIDI 头部。
- `contentValidation`：按源谱计划逐声部检查小节数、声部数、允许谱号、歌词及连续整小节休止区间；定位未解决的空小节，检查整小节休止的起点及时值。渲染**全部校对页**，检查近乎空白页和缺少五线谱。严重问题返回退出码 3 / `failed_content_validation`，留下的文件是诊断结果，不是验收通过。
- `playbackValidation`：设置导入后的乐器 ID、通道程序号与工程音源，再让 MuseScore 重新保存 MSCZ；从最终 MSCZ 新导出 MIDI，逐个发声音符核验实际程序号、bank 和声部通道。无论是否请求交付 MIDI 都执行；音色错误返回退出码 4 / `failed_playback_validation`。
- `layoutValidation`：核验重新保存后的断点是否符合选定排版策略，失败返回退出码 5 / `failed_layout_validation`。这不代替全部校对页的视觉检查。
- `savedContentValidation`：将最终 MSCZ 重新导出为 MusicXML，再次按源谱预期检查声部、小节、谱号、歌词及休止区间。不能只核对原始识别 MXL，因为它不能反映导入或后续修改后的成品。
- `measureNumberValidation`：先扫描最终 `score.mscx` 的所有 Staff。任一 `<noOffset>` 非零、手工 `<MeasureNumber>` 或编号模式覆盖都视为失败。必须先修复实际小节结构：多余的隐藏小节、重复小节、错误的多小节休止跨度或时值；结构与基准一致后，删除所有编号补偿，再重新渲染核对每个系统起始编号。
- `correctionWorklist`：草稿验证错误按类型去重，关联源页、校对页、声部和小节索引。Skill 必须先按工作单尝试有依据的自动校正并重新验证，不能把第一版错误草稿直接当作任务终点。
- 继续查看全部校对页：错误标签、文字重叠、重复速度、遗漏系统、页脚侵入。自动检查不具备可靠的文字框碰撞或完整音符语义验证。若视觉发现严重问题，即使脚本通过，也要明确报告内容不通过。
- 不因谱号变化、谱表减少或页数变化本身断言错误，核对源谱是否允许。不要自动删除疑似歌词／版权文字或音符以通过检查；保留原始识别结果，需要时修正副本再验证。
- 草稿模式报告 `editable_draft_needs_correction` 或 `editable_draft_ready_for_review`，保留所有检查错误且 `acceptancePassed=false`；它可以作为校正起点，不能称作成品。严格模式只有技术、已配置结构、播放音色和布局检查全部通过，才报告 `completed_needs_manual_review`。披露未知预期和未检查项目，并按 [人工清单](references/correction-checklist.md) 校对节拍、附点、临时记号、连线、歌词与多声部，并试听。

交付各组的 `score.mscz`、`score-proof.pdf`、可选 MIDI、MusicXML 和报告，注明对应源页。测试见 [tests/README.md](tests/README.md)。卸载只删除安装的 Skill 目录，不删除乐谱，也不卸载 Audiveris 或 MuseScore。

