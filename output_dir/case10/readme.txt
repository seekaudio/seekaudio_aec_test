[测试用例 10 / Test case 10]

素材来源：取自微软 AEC Challenge 数据集：near/far 分别为 `uNwyJZXU00eLpxsYOkGEFA_doubletalk_with_movement` 的 `_mic.wav` 与 `_lpb.wav`（密集双讲）。
人工试听标注的场景边界：
回声段：0.63–1.96 秒
近端单讲：3.08–3.62 秒，5.16–5.7 秒，7.36–7.91 秒
双讲：1.97–3.07 秒，3.63–5.15 秒，5.7–7.3 秒，7.96–10.68 秒

评测命令（将本目录 wav、log.txt 与 tools 下的 AECMOS 模型放入同一目录后执行）：
python aec_report.py --echo 0.63:1.96 --near 3.08:3.62,5.16:5.7,7.36:7.91 --dt 1.97:3.07,3.63:5.15,5.7:7.3,7.96:10.68
python aec_report_en.py --echo 0.63:1.96 --near 3.08:3.62,5.16:5.7,7.36:7.91 --dt 1.97:3.07,3.63:5.15,5.7:7.3,7.96:10.68

本用例的图文分析（主观 + 客观）见 docs/cases/case10/（中英双语）。

--------------------------------------------------------------------

Material: Material from the Microsoft AEC Challenge dataset: near/far are the `_mic.wav` and `_lpb.wav` of `uNwyJZXU00eLpxsYOkGEFA_doubletalk_with_movement` (dense double-talk).
Scene boundaries annotated by listening:
Echo: 0.63-1.96 s
Near-end single-talk: 3.08-3.62 s, 5.16-5.7 s, 7.36-7.91 s
Double-talk: 1.97-3.07 s, 3.63-5.15 s, 5.7-7.3 s, 7.96-10.68 s

Report commands (put this folder's wav files, log.txt and the AECMOS model from tools/ in one directory, then run):
python aec_report.py --echo 0.63:1.96 --near 3.08:3.62,5.16:5.7,7.36:7.91 --dt 1.97:3.07,3.63:5.15,5.7:7.3,7.96:10.68
python aec_report_en.py --echo 0.63:1.96 --near 3.08:3.62,5.16:5.7,7.36:7.91 --dt 1.97:3.07,3.63:5.15,5.7:7.3,7.96:10.68

Full illustrated analysis (subjective + objective) of this case: docs/cases/case10/ (CN / EN).
