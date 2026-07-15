[测试用例 1 / Test case 1]

素材来源：实录测试素材，约 36.8 秒。
人工试听标注的场景边界：
回声段：0–10 秒
近端单讲：10–26 秒
双讲：26–36 秒

评测命令（将本目录 wav、log.txt 与 tools 下的 AECMOS 模型放入同一目录后执行）：
python aec_report.py --echo 0:10 --near 10:26 --dt 26:36
python aec_report_en.py --echo 0:10 --near 10:26 --dt 26:36

本用例的图文分析（主观 + 客观）见 docs/cases/case1/（中英双语）。

--------------------------------------------------------------------

Material: Recorded test clip, ~36.8 s.
Scene boundaries annotated by listening:
Echo: 0-10 s
Near-end single-talk: 10-26 s
Double-talk: 26-36 s

Report commands (put this folder's wav files, log.txt and the AECMOS model from tools/ in one directory, then run):
python aec_report.py --echo 0:10 --near 10:26 --dt 26:36
python aec_report_en.py --echo 0:10 --near 10:26 --dt 26:36

Full illustrated analysis (subjective + objective) of this case: docs/cases/case1/ (CN / EN).
