# 导入后的播放音色与 MIDI 验证

声部名称、谱号和 Instrument ID 并不足以证明实际播放音色正确。必须在 MuseScore 导入后设置播放通道，并重新保存、导出 MIDI 验证。

在已核对的页组计划 `groups` 项中加入 `"playbackInstruments": ["violin", "violin", "viola", "cello"]`，按源谱声部顺序填写。单独大提琴分谱填 `["cello"]`，钢琴填 `["piano"]`（一个声部可有两个谱表）。只能根据源谱确定预期。

未显式填写时，仅对明确的 Violin I/II、Viola、Cello/Violoncello、Piano 等名称推断；无法识别时退出 4，要求补充映射。不得仅因有四个声部就当作弦乐四重奏。目前自动映射支持 violin、viola、cello、piano，其他乐器需扩展映射后验证。

| 乐器 | MIDI 原始程序号（0 起） | GM 显示编号（1 起） |
|---|---:|---:|
| Violin I / II | 40 | 41 |
| Viola | 41 | 42 |
| Cello | 42 | 43 |
| Piano | 0 | 1 |

## 强制流程

1. MusicXML 导入为 `score-imported.mscz`，保留识别原件。
2. `score-playback.py apply` 创建 `score-playback.mscz`：同步 Instrument ID、sound ID、Channel program 和 GM bank；使用工程内的 MuseScore Basic 音源配置，清除该副本中遗留的轨道音源覆盖，保留音符、谱表、音量和声像。记录 `playback-assignment.json`，不修改全局音源设置。
3. MuseScore 将该副本重新保存为最终 `score.mscz`，再导出校对 PDF 和可选 `score.mid`。
4. `verify-output.ps1` 每次都从最终 MSCZ 新导出一份 `verify-playback-*.mid`；即使没有请求交付 MIDI 也执行。若交付 `score.mid`，还要独立检查该文件。
5. 按首次分配报告冻结的声部顺序与乐器核验保存后的 ID、主通道程序号、音源配置，以及 MIDI 每个 Note On 当时生效的程序号和 bank。缺少程序设置、回退钢琴、错轨、跨声部共用通道或打击乐通道均不通过。

失败返回 `failed_playback_validation` / 退出码 4，不得报告完成。`verification.playbackValidation` 给出声部、MIDI 通道、实际程序号、预期程序号及音符数量。

当前严格检查普通弓奏；有中途换乐器、pizzicato/tremolo 实际程序切换的作品需进一步按演奏法核对，不自动抹除变化来通过检查。通过 MIDI 检查说明已核验路由和程序号，不能证明本机扬声器、音色库质量或全部音符正确，仍需试听。

## 既有 MSCZ 修复副本

用绝对路径运行 `score-playback.py apply --score <原MSCZ> --selection <selection.json> --output <新MSCZ> --report <新assignment.json>`。用 MuseScore 把新 MSCZ 另存为最终副本并导出 MIDI，再运行 `score-playback.py verify --score <最终副本> --selection <selection.json> --assignment <assignment.json> --midi <导出MIDI> --report <新验证JSON>`。Python 路径取 `config.local.json`。不要覆盖原件；旧报告没有音色检查，不代表已通过新版验证。
