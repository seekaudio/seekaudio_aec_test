[测试用例 7 / Test case 7]

素材来源：取自微软 AEC Challenge 数据集：near/far 分别为 `0RUf4sZjqUe862S4gVpZlA_doubletalk_with_movement` 的 `_mic.wav` 与 `_lpb.wav`（带走动的双讲样本，回声电平极低：−39.8 dBFS）。
人工试听标注的场景边界：
回声段：1.9–11.1 秒
近端单讲：11.2–28 秒
双讲：28–36.95 秒

评测命令（将本目录 wav、log.txt 与 tools 下的 AECMOS 模型放入同一目录后执行）：
python aec_report.py --echo 1.9:11.1 --near 11.2:28 --dt 28:36.95
python aec_report_en.py --echo 1.9:11.1 --near 11.2:28 --dt 28:36.95

本用例的图文分析（主观 + 客观）见 docs/cases/case7/（中英双语）。

--------------------------------------------------------------------

Material: Material from the Microsoft AEC Challenge dataset: near/far are the `_mic.wav` and `_lpb.wav` of `0RUf4sZjqUe862S4gVpZlA_doubletalk_with_movement` (double-talk with movement; very low echo level: -39.8 dBFS).
Scene boundaries annotated by listening:
Echo: 1.9-11.1 s
Near-end single-talk: 11.2-28 s
Double-talk: 28-36.95 s

Report commands (put this folder's wav files, log.txt and the AECMOS model from tools/ in one directory, then run):
python aec_report.py --echo 1.9:11.1 --near 11.2:28 --dt 28:36.95
python aec_report_en.py --echo 1.9:11.1 --near 11.2:28 --dt 28:36.95

Full illustrated analysis (subjective + objective) of this case: docs/cases/case7/ (CN / EN).
