[测试用例 8 / Test case 8]

素材来源：取自微软 AEC Challenge 数据集：near/far 分别为 `mAVjs9dULk24wBwJUyuzcw_doubletalk_with_movement` 的 `_mic.wav` 与 `_lpb.wav`。
人工试听标注的场景边界：
回声段：0–11 秒，30.6–37.4 秒
近端单讲：15.5–27.4 秒
双讲：27.4–30.5 秒

评测命令（将本目录 wav、log.txt 与 tools 下的 AECMOS 模型放入同一目录后执行）：
python aec_report.py --echo 0:11,30.6:37.4 --near 15.5:27.4 --dt 27.4:30.5
python aec_report_en.py --echo 0:11,30.6:37.4 --near 15.5:27.4 --dt 27.4:30.5

本用例的图文分析（主观 + 客观）见 docs/cases/case8/（中英双语）。

--------------------------------------------------------------------

Material: Material from the Microsoft AEC Challenge dataset: near/far are the `_mic.wav` and `_lpb.wav` of `mAVjs9dULk24wBwJUyuzcw_doubletalk_with_movement`.
Scene boundaries annotated by listening:
Echo: 0-11 s, 30.6-37.4 s
Near-end single-talk: 15.5-27.4 s
Double-talk: 27.4-30.5 s

Report commands (put this folder's wav files, log.txt and the AECMOS model from tools/ in one directory, then run):
python aec_report.py --echo 0:11,30.6:37.4 --near 15.5:27.4 --dt 27.4:30.5
python aec_report_en.py --echo 0:11,30.6:37.4 --near 15.5:27.4 --dt 27.4:30.5

Full illustrated analysis (subjective + objective) of this case: docs/cases/case8/ (CN / EN).
