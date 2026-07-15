[测试用例 9 / Test case 9]

素材来源：取自微软 AEC Challenge 数据集：near/far 分别为 `uL3BLytnwEuieb6jpcG9tQ_doubletalk_with_movement` 的 `_mic.wav` 与 `_lpb.wav`（密集交替双讲）。
人工试听标注的场景边界：
回声段：0.62–1.48 秒
近端单讲：2.27–2.91 秒，9.0–9.66 秒
双讲：1.49–2.27 秒，2.92–4.92 秒，5.5–9.0 秒，9.7–12.76 秒

评测命令（将本目录 wav、log.txt 与 tools 下的 AECMOS 模型放入同一目录后执行）：
python aec_report.py --echo 0.62:1.48 --near 2.27:2.91,9.0:9.66 --dt 1.49:2.27,2.92:4.92,5.5:9.0,9.7:12.76
python aec_report_en.py --echo 0.62:1.48 --near 2.27:2.91,9.0:9.66 --dt 1.49:2.27,2.92:4.92,5.5:9.0,9.7:12.76

本用例的图文分析（主观 + 客观）见 docs/cases/case9/（中英双语）。

--------------------------------------------------------------------

Material: Material from the Microsoft AEC Challenge dataset: near/far are the `_mic.wav` and `_lpb.wav` of `uL3BLytnwEuieb6jpcG9tQ_doubletalk_with_movement` (dense alternating double-talk).
Scene boundaries annotated by listening:
Echo: 0.62-1.48 s
Near-end single-talk: 2.27-2.91 s, 9.0-9.66 s
Double-talk: 1.49-2.27 s, 2.92-4.92 s, 5.5-9.0 s, 9.7-12.76 s

Report commands (put this folder's wav files, log.txt and the AECMOS model from tools/ in one directory, then run):
python aec_report.py --echo 0.62:1.48 --near 2.27:2.91,9.0:9.66 --dt 1.49:2.27,2.92:4.92,5.5:9.0,9.7:12.76
python aec_report_en.py --echo 0.62:1.48 --near 2.27:2.91,9.0:9.66 --dt 1.49:2.27,2.92:4.92,5.5:9.0,9.7:12.76

Full illustrated analysis (subjective + objective) of this case: docs/cases/case9/ (CN / EN).
