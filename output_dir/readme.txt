打开near.wav和far.wav进行播放，判断结果如下：
回音段:0-10秒
近端语音段:10-26秒
双讲段:26-36秒

评估测试命令行如下：
python aec_report.py --echo 0:10 --near 10:26 --dt 26:36
python aec_report_en.py --echo 0:10 --near 10:26 --dt 26:36




Open near.wav and far.wav for playback, and the judgment results are as follows:
Echo segment: 0–10 seconds
Near‑end speech segment: 10–26 seconds
Double‑talk segment: 26–36 seconds

The evaluation test command lines are:
python aec_report.py --echo 0:10 --near 10:26 --dt 26:36
python aec_report_en.py --echo 0:10 --near 10:26 --dt 26:36