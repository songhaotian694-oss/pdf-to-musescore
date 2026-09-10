# 页组计划 v2

助手查看所有源页后创建，不要求用户手写 JSON。明确连续谱面可自行确认；多个独立页组需要按用户给定范围处理，不重复询问已给出的选择。

预检返回 `preflight.json`、`source-thumbnails/page-NNN.png`：源哈希、每页谱表启发式、可提取的乐器名和文字。扫描页没有文本时仍需看图；脚本不会自动 OCR 谱号、小节号或标题。自动组数不等于最终判断。

下面是 8 页混合谱的示例。替换哈希并按实际源谱修改，不能套用示例小节数：

```json
{
  "schemaVersion": 2,
  "sourceSha256": "源PDF的SHA256",
  "reviewed": true,
  "reviewedPages": [1,2,3,4,5,6,7,8],
  "selectionBasis": "user",
  "groups": [
    {"id":"full-score","pages":[1,2,3,4],"expectedParts":4,"lyricsExpected":false,"expectedMeasuresPerPart":[28,28,28,28],"allowedClefsPerPart":[["G"],["G"],["C"],["F"]]},
    {"id":"violin-1","pages":[5],"expectedParts":1,"lyricsExpected":false,"expectedMeasuresPerPart":[28],"allowedClefsPerPart":[["G"]]},
    {"id":"violin-2","pages":[6],"expectedParts":1,"lyricsExpected":false,"expectedMeasuresPerPart":[28],"allowedClefsPerPart":[["G"]]},
    {"id":"viola","pages":[7],"expectedParts":1,"lyricsExpected":false,"expectedMeasuresPerPart":[28],"allowedClefsPerPart":[["C"]]},
    {"id":"violoncello","pages":[8],"expectedParts":1,"lyricsExpected":false,"expectedMeasuresPerPart":[28],"allowedClefsPerPart":[["F"]]}
  ]
}
```

- 所有组覆盖全部源页且不重叠，组内升序。选择一个组不处理其他组。封面等非乐谱页先制作明确记录来源页码的乐谱副本再预检，不将封面作为乐谱组。
- `expectedParts` 是 MusicXML 乐器声部数；钢琴左右手通常是 1 part、2 staves。
- `playbackInstruments` 按源谱声部顺序明确播放乐器：四重奏用 `["violin","violin","viola","cello"]`，大提琴分谱用 `["cello"]`，钢琴用 `["piano"]`。详见 [音色与 MIDI 验证](playback.md)。不要根据识别结果的错误音色反推该字段。
- `expectedMeasuresPerPart` 按声部顺序填写真实小节数（考虑弱起和分段小节），不可把全体声部节点总数当作乐曲长度。未知用 null，报告会披露未检查。
- `allowedClefsPerPart` 每个声部列出源谱允许的谱号，例如大提琴确有高音谱号则填写 `["F","G"]`。未知用 null。
- `selectionBasis` 单份明确连续谱可为 `unambiguous_visual_review`；多独立页组为 `user`，表示按真实用户选择处理。不得伪称用户已选择。
- 跨越自动检测边界的连续组需 `continuityReason` 说明视觉证据，例如小节号连续、配器临时减少；不能借此强行串接独立分谱。
- 源 PDF 变化后重新预检，哈希不匹配拒绝执行。

对各组分别传 `-GroupId`，建议父目录用 `输出/full-score`、`输出/violin-1` 等。源小节或文字若无法确定，应保留不确定性，不伪造识别精度。
