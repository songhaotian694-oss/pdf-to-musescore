# 空小节、整小节休止和多小节休止

多小节休止线上方的数字是休止的小节数，不能当成一小节，也不能把已经展开的 MusicXML 再展开一次。整小节休止的时值跟随当前拍号：3/4 为 3 个四分音符时值，12/8 为 6 个；不能一律写 4。

## 从源谱记录预期

查看每页源谱，按实际时间顺序记录**完整的连续整小节休止区间**，包括开头和结尾。相邻休止即使在排练号、换行或变拍处分成几个符号，也合并成一个连续区间；拍号改变仍要单独校对。数清休止后的进入小节并用排练号和前后音型交叉确认。

在组计划中加入 `expectedRestSpansPerPart`，一个 MusicXML part 对应一个列表。例如一份分谱开头休止 8 小节，第 25、27、29 小节各休止一小节：

```json
"expectedRestSpansPerPart": [[
  {"startMeasure": 1, "measureCount": 8},
  {"startMeasure": 25, "measureCount": 1},
  {"startMeasure": 27, "measureCount": 1},
  {"startMeasure": 29, "measureCount": 1}
]]
```

`startMeasure` 从所选乐谱第一个实际小节按 1 起计数，包含弱起；它不是可任意修改的显示小节号。钢琴左右手属于同一 part 时，只有两手都整小节休止才计入该 part 的休止区间。`[[]]` 表示已核对该声部没有整小节休止；`null` 或省略表示未知，报告会明确披露未验证源休止数量和进入位置。不要把局部核对结果伪装成完整列表。源谱含多小节休止时，在完成区间核对前不能声称其时间轴通过验收。

## 自动检查和修复边界

原始 MXL 和最终 MSCZ 重新导出的 MusicXML 都检查：

- 无有时值音符或休止的小节，报告声部、实际序号与显示小节号。只有 forward 或倚音不能证明原谱是休止，需人工解决后再验收。
- `rest measure="yes"` 的起点及时值，使用继承的 divisions 和拍号，处理 backup；弱起／无拍号等情况披露未完成的时值检查。
- `multiple-rest` 标注是否有对应的实际休止小节。MusicXML 的 `measure` 节点只计一次，MSCX 中的多小节休止显示代理也不能当成真实小节另加一次。以 MuseScore 导出的 MusicXML 和源谱实际小节为准。
- 实际连续休止区间是否等于源谱预期。隐藏休止仍占播放时间，不能忽略；全休止声部的 MIDI 可能没有 Note On，播放验证保留乐器设置检查并单独报告这些谱表。

验证失败返回内容错误码 3，保存原始结果。修复时在副本中根据源谱纠正缺失／多余的实际休止、拍号和前后进入位置，再导入、重导 MusicXML、MIDI 和校对谱。不要靠修改显示小节号、隐藏多出的休止、取消多小节合并或关闭验证掩盖时长错误；不能无依据自动填充或删除小节。录音或 MIDI 程序号正确也不能证明进入时间正确。

这些规则不检查所有音符的节奏，不自动从图片读取休止数，也不能保证 OMR 没有把音符误作休止；源谱区间核对和试听仍是必要步骤。

格式依据：[MusicXML rest](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/rest/)、[multiple-rest](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/multiple-rest/)。
