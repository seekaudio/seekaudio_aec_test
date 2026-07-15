[测试用例 2 / Test case 2]

素材来源：实录测试素材，约 40 秒的长样本；开头为近端单讲，中段为长双讲，后段为回声。
人工试听标注的场景边界：
回声段：6–8 秒，26–40 秒
近端单讲：0–6.3 秒
双讲：8–24.6 秒

评测命令（将本目录 wav、log.txt 与 tools 下的 AECMOS 模型放入同一目录后执行）：
python aec_report.py --echo 6:8,26:40 --near 0:6.3 --dt 8:24.6
python aec_report_en.py --echo 6:8,26:40 --near 0:6.3 --dt 8:24.6

本用例的图文分析（主观 + 客观）见 docs/cases/case2/（中英双语）。

--------------------------------------------------------------------

Material: Recorded ~40 s long clip: near-end single-talk first, a long double-talk middle, echo at the end.
Scene boundaries annotated by listening:
Echo: 6-8 s, 26-40 s
Near-end single-talk: 0-6.3 s
Double-talk: 8-24.6 s

Report commands (put this folder's wav files, log.txt and the AECMOS model from tools/ in one directory, then run):
python aec_report.py --echo 6:8,26:40 --near 0:6.3 --dt 8:24.6
python aec_report_en.py --echo 6:8,26:40 --near 0:6.3 --dt 8:24.6

Full illustrated analysis (subjective + objective) of this case: docs/cases/case2/ (CN / EN).
