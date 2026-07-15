[测试用例 3 / Test case 3]

素材来源：取自微软 AEC Challenge 数据集：near/far 分别为 `fbkhafa8n0W-W8ytgzClpg_doubletalk_with_movement` 的 `_mic.wav` 与 `_lpb.wav`（带走动的双讲样本）。
人工试听标注的场景边界：
回声段：0.93–1.8 秒，7.35–8 秒
近端单讲：6.85–7.33 秒，9.39–10.45 秒
双讲：1.76–6.84 秒，8–9.38 秒，10.45–11.18 秒

评测命令（将本目录 wav、log.txt 与 tools 下的 AECMOS 模型放入同一目录后执行）：
python aec_report.py --echo 0.93:1.8,7.35:8 --near 6.85:7.33,9.39:10.45,11.25:12.1 --dt 1.76:6.84,8:9.38,10.45:11.18
python aec_report_en.py --echo 0.93:1.8,7.35:8 --near 6.85:7.33,9.39:10.45,11.25:12.1 --dt 1.76:6.84,8:9.38,10.45:11.18

本用例的图文分析（主观 + 客观）见 docs/cases/case3/（中英双语）。

--------------------------------------------------------------------

Material: Material from the Microsoft AEC Challenge dataset: near/far are the `_mic.wav` and `_lpb.wav` of `fbkhafa8n0W-W8ytgzClpg_doubletalk_with_movement` (double-talk with movement).
Scene boundaries annotated by listening:
Echo: 0.93-1.8 s, 7.35-8 s
Near-end single-talk: 6.85-7.33 s, 9.39-10.45 s
Double-talk: 1.76-6.84 s, 8-9.38 s, 10.45-11.18 s

Report commands (put this folder's wav files, log.txt and the AECMOS model from tools/ in one directory, then run):
python aec_report.py --echo 0.93:1.8,7.35:8 --near 6.85:7.33,9.39:10.45,11.25:12.1 --dt 1.76:6.84,8:9.38,10.45:11.18
python aec_report_en.py --echo 0.93:1.8,7.35:8 --near 6.85:7.33,9.39:10.45,11.25:12.1 --dt 1.76:6.84,8:9.38,10.45:11.18

Full illustrated analysis (subjective + objective) of this case: docs/cases/case3/ (CN / EN).
