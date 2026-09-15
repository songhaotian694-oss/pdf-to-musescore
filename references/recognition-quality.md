# 自动提高识别质量

用户只需提供 PDF 和确认页组。转换默认使用 `-RecognitionProfile auto`：

1. 先直接识别选定的原始 PDF，避免不必要的图像损失；
2. 若原始结果未通过已复核的结构检查，自动生成 400 DPI 灰度 PDF；
3. 灰度版本只做轻微自动对比度调整，不锐化、不拉伸、不修改符号形状；
4. 再运行一次 Audiveris，根据源谱计划中的声部数、小节数、谱号、歌词和休止检查计算候选罚分；
5. 优先选择通过结构检查的候选；都未通过时选择罚分较低者，平分保留原始 PDF 结果。

`report.json` 的 `recognitionAttempts` 保存每次识别的输入、退出码、MusicXML、错误与 `qualityPenalty`，`selectedRecognitionProfile` 记录实际选择。候选比较不衡量音高、时值、连线或完整音乐语义，因此不能把较低罚分称为准确率更高。

如果需要速度或可复现的原始行为，使用 `-RecognitionProfile original`，不运行灰度回退。自动回退可能使 Audiveris 运行时间接近两倍，并增加临时文件体积；只有原始结果结构检查失败时才会触发。

当两个候选均有严重问题时，保留 `.omr`，在 Audiveris 中先修正谱表线、系统、声部分组、小节线、谱号和拍号，再导出 MusicXML。不要根据错误 OMR 修改源谱预期来降低罚分。
