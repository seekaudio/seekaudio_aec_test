[测试用例 4 / Test case 4]

素材来源：取自微软 AEC Challenge 数据集：near/far 分别为 `DNb0qIMRg0iwJqiYFx6RbA_doubletalk` 的 `_mic.wav` 与 `_lpb.wav`。
人工试听标注的场景边界：
回声段：1.6–2.24 秒
近端单讲：9–9.65 秒
双讲：2.25–9 秒，9.66–11.02 秒

评测命令（将本目录 wav、log.txt 与 tools 下的 AECMOS 模型放入同一目录后执行）：
python aec_report.py --echo 1.6:2.24 --near 9:9.65 --dt 2.25:9,9.66:11.02
python aec_report_en.py --echo 1.6:2.24 --near 9:9.65 --dt 2.25:9,9.66:11.02

本用例的图文分析（主观 + 客观）见 docs/cases/case4/（中英双语）。

--------------------------------------------------------------------

Material: Material from the Microsoft AEC Challenge dataset: near/far are the `_mic.wav` and `_lpb.wav` of `DNb0qIMRg0iwJqiYFx6RbA_doubletalk`.
Scene boundaries annotated by listening:
Echo: 1.6-2.24 s
Near-end single-talk: 9-9.65 s
Double-talk: 2.25-9 s, 9.66-11.02 s

Report commands (put this folder's wav files, log.txt and the AECMOS model from tools/ in one directory, then run):
python aec_report.py --echo 1.6:2.24 --near 9:9.65 --dt 2.25:9,9.66:11.02
python aec_report_en.py --echo 1.6:2.24 --near 9:9.65 --dt 2.25:9,9.66:11.02

Full illustrated analysis (subjective + objective) of this case: docs/cases/case4/ (CN / EN).
