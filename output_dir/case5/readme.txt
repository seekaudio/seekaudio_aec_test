[测试用例 5 / Test case 5]

素材来源：取自微软 AEC Challenge 数据集：near/far 分别为 `FGqMw1OM4Um5uvmHahuZbg_farend_singletalk` 的 `_mic.wav` 与 `_lpb.wav`。样本只有回声，没有近端与双讲。
人工试听标注的场景边界：
回声段：0–11.22 秒

评测命令（将本目录 wav、log.txt 与 tools 下的 AECMOS 模型放入同一目录后执行）：
python aec_report.py --echo 0:11.22 --no-auto
python aec_report_en.py --echo 0:11.22 --no-auto

本用例的图文分析（主观 + 客观）见 docs/cases/case5/（中英双语）。

--------------------------------------------------------------------

Material: Material from the Microsoft AEC Challenge dataset: near/far are the `_mic.wav` and `_lpb.wav` of `FGqMw1OM4Um5uvmHahuZbg_farend_singletalk`. Echo only - no near-end or double-talk.
Scene boundaries annotated by listening:
Echo: 0-11.22 s

Report commands (put this folder's wav files, log.txt and the AECMOS model from tools/ in one directory, then run):
python aec_report.py --echo 0:11.22 --no-auto
python aec_report_en.py --echo 0:11.22 --no-auto

Full illustrated analysis (subjective + objective) of this case: docs/cases/case5/ (CN / EN).
