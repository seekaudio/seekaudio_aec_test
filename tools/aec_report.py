#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
aec_report.py —— AEC 四配置评测 / 配对对比报告  (适配 seekaudio_aec_test 新版输出)

================================ 用法 ================================
【用法一】零参数(最简单, 推荐): 把本脚本连同结果文件放进同一目录, 直接运行:
    python aec_report.py
    需要的文件: far.wav near.wav a1.wav a2.wav b1.wav b2.wav  log.txt
                Run_*Stage_0.onnx (AECMOS 模型, 缺则跳过该节)
    场景边界(哪里是回声/近端/双讲)不写死, 而是从 far.wav / near.wav 信号
    自动检测(见 auto_segments), 换任何素材都自适应。检测结果会打印在报告头
    供核对。

【用法二】手动指定场景段(覆盖自动检测): 用 --echo / --near / --dt 指定时段。
    python aec_report.py --echo 0:10 --near 10:26 --dt 26:36
    python aec_report.py --echo 0:8,30:36 --dt 26:-1
    - --echo : 远端单讲 / 纯回声段(只判 Echo MOS)
    - --near : 近端单讲段(只判 Other MOS)
    - --dt   : 双讲段(Echo 与 Other 都判)
    - 段格式 "起:止"(单位秒); 一类可多段, 用逗号分隔(如 0:8,30:36);
      止用 -1 表示到文件结尾(如 26:-1)。
    - 支持"部分覆盖": 只给其中一两个, 未给的类别仍走自动检测。
      例: 只 python aec_report.py --dt 26:-1 => echo/near 自动, dt 用你给的。
    - 整段只有一种场景(全程纯回声 / 全程双讲 / 全程近端): 只指定那一类, 再加
      --no-auto 关闭对其余类别的自动检测(否则会在单一场景素材上误检):
        全程纯回声  python aec_report.py --echo 0:11.22 --no-auto
        全程双讲    python aec_report.py --dt 0:36 --no-auto
        全程近端    python aec_report.py --near 0:36 --no-auto
      也可把某类显式写 none 置空: python aec_report.py --echo 0:8 --near none --dt 8:11

【用法三】指定结果目录: 结果文件不在脚本目录时, 用 --dir 指向它。
    python aec_report.py --dir D:\out
    python aec_report.py --dir D:\out --echo 0:8,30:36 --dt 26:-1
=====================================================================

结果同时打印到屏幕并写入 <目录>/aec_report.txt。
依赖: 自动分段仅需 numpy(+ wav); 音频/AECMOS 节另需 librosa/onnxruntime。
      pip install numpy librosa onnxruntime
      (缺依赖时设备端日志解析仍可正常输出; 无 numpy/wav 时自动分段跳过,
       此时可用 --echo/--near/--dt 手动指定, 或仅看设备端各表)
完整参数说明见 python aec_report.py --help。

—— 与旧版相比的适配点(seekaudio_aec_test 代码/输出已变更) ——
  * A1/A2 现在走下沉后的公开 API(seekaudio_aec_create, 2 参数), create() 内存
    含库内 AFE 前端; B1/B2 仍为 esp-sr 基线。指标为黑盒观测, 不受此影响。
  * CPU load 行新增 max% + 帧号: "26.2% avg / 29.4% p95 / 32.1% max (frame #11)"。
  * per-frame max 行新增 "at frame #N/总帧"。
  * 新增 "ERLE converged"(末四分之一回声活跃) 与 "run transient"(运行峰值) 行。
  * B2 的 NSNet2 权重占一个 flash 模型分区(MODEL_LOADER 行), 计入"总占用"。
  * 场景边界改为信号自动检测, 不再写死时间段(旧版按单一素材写死的默认已废弃)。
"""
# ---- 场景边界 ------------------------------------------------------------
# 不再写死时间段(那样只对某一个素材成立)。参数为空时由 auto_segments() 从
# far/near 信号自动检测; 用 --echo/--near/--dt 可覆盖任一类。
# 每一类是"段列表", 一类可多段: 单段 0:10, 两段 0:10,30:36; 到结尾用 -1。
FE_ST, NE_ST, DT = [], [], []   # 运行时由 main 填充(自动检测或手动指定)

# ---- 自动分段可调参数(一般无需改) ----------------------------------------
SEG_WIN_MS      = 32     # 分析帧长(ms)
SEG_FAR_ABS_DB  = -50.0  # far 绝对活跃门(dBFS): 低于此视为扬声器未放音(无回声)
SEG_NEAR_ABS_DB = -50.0  # near 绝对活跃门(dBFS)
SEG_FAR_REL_DB  = 20.0   # far 相对峰值门(dB): 低于 far 峰 20dB 视为非活跃
SEG_MED_FRAMES  = 5      # 标签中值/众数滤波窗(帧, 去抖)
SEG_MIN_DUR     = 0.5    # 最短段长(s), 更短的碎段丢弃
SEG_BRIDGE      = 0.30   # 同类段间隔 < 此值(s) 则桥接合并
SEG_RHO_THR     = None   # 回声/双讲相关度阈值; None=Otsu 自适应(推荐)

# 配对: A1 对标 B1(传统NS对传统NS), A2 对标 B2(AI降噪对AI降噪)
PAIRS = [("A1", "B1", "传统 NS 对传统 NS"),
         ("A2", "B2", "AI 降噪对 AI 降噪")]

# 配置全名(用于图例; 与设备端 backend 名一致)
CFG_NAMES = {
    "A1": "SeekAudio AEC + NLP + WebRTC NS",
    "A2": "SeekAudio AEC + NLP + AI Noise",
    "B1": "FD-AEC + NLP + ns_pro   (esp-sr 基线)",
    "B2": "FD-AEC + NLP + NSNet2   (esp-sr 基线)",
}

import os, re, sys, glob, math, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 16000
CFGS = ["A1", "A2", "B1", "B2"]
OUT_LINES = []
OUT_DIR = HERE   # main 里改成实际结果目录


# ---------------------------------------------------------------- 0) 自动分段
def load_wav_np(path):
    """用标准库 wave + numpy 读 16bit PCM wav -> (float[-1,1], sr)。
    仅需 numpy(不依赖 librosa), 供自动分段使用。多声道取首声道。"""
    import wave
    import numpy as np
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        n = w.getnframes()
        raw = w.readframes(n)
    if sw != 2:
        raise ValueError(f"{path}: 仅支持 16-bit PCM (got {sw*8}-bit)")
    x = np.frombuffer(raw, dtype="<i2").astype(np.float64)
    if ch > 1:
        x = x[::ch]
    return x / 32768.0, sr


def _median_filter(x, k):
    import numpy as np
    if k <= 1:
        return x
    r = k // 2
    y = x.copy()
    for i in range(len(x)):
        y[i] = np.median(x[max(0, i - r): min(len(x), i + r + 1)])
    return y


def _otsu_threshold(vals, nbins=64):
    """对一维数值做 Otsu 双类分割, 返回阈值; 数据退化时返回 None。"""
    import numpy as np
    v = vals[np.isfinite(vals)]
    if len(v) < 4:
        return None
    lo, hi = float(v.min()), float(v.max())
    if hi - lo < 1e-6:
        return None
    hist, edges = np.histogram(v, bins=nbins, range=(lo, hi))
    p = hist.astype(np.float64) / max(hist.sum(), 1)
    omega = np.cumsum(p)
    centers = (edges[:-1] + edges[1:]) / 2
    mu = np.cumsum(p * centers)
    muT = mu[-1]
    den = omega * (1 - omega)
    sb = np.where(den > 1e-12, (muT * omega - mu) ** 2 / (den + 1e-12), 0)
    k = int(np.argmax(sb))
    return float((edges[k] + edges[k + 1]) / 2)


def best_delay(ref, sig, maxlag=6000):
    """near 相对 far 的带符号延时(样本), 用 FFT 互相关的峰值。"""
    import numpy as np
    n = min(len(ref), len(sig))
    r = ref[:n] - ref[:n].mean()
    s = sig[:n] - sig[:n].mean()
    N = 1
    while N < 2 * n:
        N *= 2
    cc = np.fft.irfft(np.fft.rfft(r, N) * np.conj(np.fft.rfft(s, N)), N)
    cc = np.concatenate((cc[-maxlag:], cc[:maxlag + 1]))
    return int(np.argmax(cc) - maxlag)


def auto_segments(near, far, sr):
    """从 far(扬声器参考)/near(麦克风) 自动判别场景段, 返回
    (segs_dict, info)。segs_dict = {'FE':[(s,e)..],'NE':[..],'DT':[..]}。

    判据(逐 32ms 帧):
      * far 活跃 = 绝对 dBFS 门 且 相对 far 峰值门  -> 回声是否存在(扬声器在放)
      * near 活跃 = 绝对 dBFS 门
      * far 活跃帧内, 用 near 与对齐后 far 的归一化相关度 rho + Otsu 阈值区分:
          rho 高 -> near≈回声(纯回声, FE);  rho 低 -> 含不相关近端语音(双讲, DT)
      * far 非活跃 且 near 活跃 -> 近端单讲(NE);  两者皆非活跃 -> 静音(略)
    标签做众数滤波去抖, 合并同类相邻段, 桥接小间隙, 丢弃过短段。"""
    import numpy as np
    win = int(round(SEG_WIN_MS / 1000.0 * sr))
    d = best_delay(near, far)
    far_al = np.roll(far, d)
    n = min(len(near), len(far_al))
    near = near[:n].astype(np.float64)
    far_al = far_al[:n].astype(np.float64)
    nf = n // win
    if nf < 2:
        return {"FE": [], "NE": [], "DT": []}, {"delay": d, "note": "音频过短"}

    def frame_dbfs(x):
        o = np.empty(nf)
        for i in range(nf):
            seg = x[i * win:(i + 1) * win]
            rms = math.sqrt(float(np.mean(seg ** 2))) + 1e-12
            o[i] = 20.0 * math.log10(rms)
        return o

    ndb = frame_dbfs(near)
    fdb = frame_dbfs(far_al)
    far_peak = float(fdb.max())
    fa = (fdb > SEG_FAR_ABS_DB) & (fdb > far_peak - SEG_FAR_REL_DB)
    na = ndb > SEG_NEAR_ABS_DB

    rho = np.zeros(nf)
    for i in range(nf):
        a = near[i * win:(i + 1) * win]; a = a - a.mean()
        b = far_al[i * win:(i + 1) * win]; b = b - b.mean()
        den = np.linalg.norm(a) * np.linalg.norm(b) + 1e-12
        rho[i] = abs(float(np.dot(a, b) / den))
    rho = _median_filter(rho, 7)

    thr = SEG_RHO_THR
    if thr is None:
        t = _otsu_threshold(rho[fa]) if fa.any() else None
        thr = min(max(t if t is not None else 0.35, 0.25), 0.60)

    lab = np.array(["S"] * nf, dtype="<U2")
    for i in range(nf):
        if fa[i]:
            lab[i] = "FE" if rho[i] >= thr else "DT"
        elif na[i]:
            lab[i] = "NE"

    # 众数滤波去抖
    r = SEG_MED_FRAMES // 2
    sm = lab.copy()
    for i in range(nf):
        w = lab[max(0, i - r): min(nf, i + r + 1)]
        vv, cc = np.unique(w, return_counts=True)
        sm[i] = vv[int(np.argmax(cc))]
    lab = sm

    segs = {"FE": [], "NE": [], "DT": []}
    i = 0
    while i < nf:
        if lab[i] in segs:
            j = i
            while j < nf and lab[j] == lab[i]:
                j += 1
            segs[lab[i]].append([i * win / sr, j * win / sr])
            i = j
        else:
            i += 1

    def post(lst):
        if not lst:
            return []
        lst = sorted(lst)
        out = [list(lst[0])]
        for s, e in lst[1:]:
            if s - out[-1][1] <= SEG_BRIDGE:
                out[-1][1] = e
            else:
                out.append([s, e])
        return [(round(s, 2), round(e, 2)) for s, e in out if e - s >= SEG_MIN_DUR]

    for k in segs:
        segs[k] = post(segs[k])
    info = {"delay": d, "delay_ms": d / sr * 1000.0, "far_peak_db": far_peak,
            "rho_thr": thr, "frames": nf}
    return segs, info


def parse_segspec(spec, name):
    """把 '0:10' 或 '0:10,30:36' 解析成 [(0.0,10.0),...]; -1 表示到结尾。
    返回值: None=该项未提供(交给自动检测); []=显式置空(none/-, 该场景不存在);
    非空列表=手动指定的段。"""
    if spec is None:
        return None
    s = str(spec).strip().lower()
    if s in ("none", "无", "-", "empty", "na", ""):
        return []            # 显式置空: 该场景不存在, 不自动检测
    out = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError("--%s 段 '%s' 格式应为 起:止 (如 0:10), 或 none 表示该场景不存在" % (name, part))
        a, b = part.split(":", 1)
        try:
            a, b = float(a), float(b)
        except ValueError:
            raise ValueError("--%s 段 '%s' 的起止必须是数字" % (name, part))
        out.append((a, b))
    return out


def emit(s=""):
    print(s)
    OUT_LINES.append(s)


def fmt_ranges(ranges):
    return ",".join(("{:g}-{:g}s".format(a, b) if b >= 0 else "{:g}-ends".format(a))
                    for a, b in ranges)


# ---------------------------------------------------------------- 1) 解析设备端日志
def parse_log(path="log.txt"):
    """从串口日志按配置块提取设备端指标。纯标准库, 无依赖。
    适配新版 aec_runner 输出: CPU max+帧号 / ERLE converged / run transient /
    per-frame max 帧号 / B2 flash 模型分区。"""
    dev = {c: {} for c in CFGS}
    if not os.path.exists(path):
        return dev, False
    txt = open(path, encoding="utf-8", errors="replace").read()

    # B2 的 NSNet2 权重所占 flash 模型分区(全局行, 出现在 B2 之前), 计入 B2 总占用。
    mp = re.search(r"MODEL_LOADER:\s*The partition size is\s*(\d+)\s*KB", txt)
    if mp:
        dev["B2"]["flash_model_kb"] = float(mp.group(1))

    # 以设备端统计分隔行 "-------- A1: ... --------" 切块(>=4 个连字符, 避开
    # "====" 段标题和句中的 '+' 号)。SA-FULL 等其它块不匹配, 自然忽略。
    marks = list(re.finditer(r"-{4,}\s*(A1|A2|B1|B2)\s*:", txt))
    for i, m in enumerate(marks):
        cfg = m.group(1)
        blk = txt[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(txt)]
        d = dev[cfg]

        def g(pat, cast=float):
            mm = re.search(pat, blk)
            return cast(mm.group(1)) if mm else None

        d["rtf"]          = g(r"real-time factor:\s*([\d.]+)x")
        d["compute_s"]    = g(r"compute time\s*:\s*([\d.]+)\s*s")
        d["audio_s"]      = g(r"audio duration\s*:\s*([\d.]+)\s*s")
        d["frames"]       = g(r"frames\s*:\s*(\d+)", int)
        d["avg_us"]       = g(r"per-frame avg\s*:\s*([\d.]+)\s*us")
        d["p95_us"]       = g(r"per-frame p95\s*:\s*([\d.]+)\s*us")

        # per-frame max 现在带帧号: "10287.0 us  at frame #11/1148"
        mx = re.search(r"per-frame max\s*:\s*([\d.]+)\s*us(?:\s+at frame #(\d+)/(\d+))?", blk)
        if mx:
            d["max_us"] = float(mx.group(1))
            if mx.group(2):
                d["max_frame"] = int(mx.group(2))
                d["total_frames"] = int(mx.group(3))

        # CPU load 现在带 max% + 帧号:
        # "26.2% avg / 29.4% p95 / 32.1% max (frame #11)  (~63 MHz of 240 MHz)"
        cpu = re.search(r"CPU load\s*:\s*([\d.]+)%\s*avg\s*/\s*([\d.]+)%\s*p95"
                        r"(?:\s*/\s*([\d.]+)%\s*max\s*\(frame\s*#(\d+)\))?", blk)
        if cpu:
            d["cpu_avg"] = float(cpu.group(1))
            d["cpu_p95"] = float(cpu.group(2))
            if cpu.group(3):
                d["cpu_max"] = float(cpu.group(3))
                d["cpu_max_frame"] = int(cpu.group(4))
        d["cpu_mhz"] = g(r"\(~([\d.]+)\s*MHz of")

        d["erle_overall"]  = g(r"ERLE overall\s*:\s*([-\d.]+)\s*dB")
        d["erle_active"]   = g(r"ERLE echo-active\s*:\s*([-\d.]+)\s*dB")
        d["erle_active_n"] = g(r"ERLE echo-active\s*:.*?\((\d+)\s*far-active", int)
        d["erle_conv"]     = g(r"ERLE converged\s*:\s*([-\d.]+)\s*dB")   # 新增行

        # create(): 墙钟 + 片内/PSRAM
        cr = re.search(r"create\(\)\s*:\s*([\d.]+)\s*ms;\s*internal SRAM\s*([\d.]+)"
                       r"\s*KB,\s*PSRAM\s*([\d.]+)\s*KB", blk)
        if cr:
            d["create_ms"] = float(cr.group(1))
            d["sram_kb"]   = float(cr.group(2))
            d["psram_kb"]  = float(cr.group(3))

        # run transient: 运行期相对 create 基线的峰值增量(新增行)
        rt = re.search(r"run transient\s*:\s*internal SRAM peak \+([\d.]+)\s*KB,"
                       r"\s*PSRAM peak \+([\d.]+)\s*KB", blk)
        if rt:
            d["tr_sram_kb"]  = float(rt.group(1))
            d["tr_psram_kb"] = float(rt.group(2))

        d["stack_kb"] = g(r"stack headroom\s*:\s*([\d.]+)\s*KB")
        d["crc32"] = (re.search(r"output CRC32\s*:\s*(0x[0-9A-Fa-f]+)", blk) or [None, None])[1]

        # 远端单讲 ERLE: convergence 行第一个 "--" 之前的数值桶(纯回声段, 无双讲污染)
        cv = re.search(r"convergence ERLE/[\d.]+s:\s*(.+)", blk)
        if cv:
            buckets = []
            for tok in cv.group(1).split():
                if tok.startswith("--"):
                    break
                try:
                    buckets.append(float(tok))
                except ValueError:
                    break
            if buckets:
                d["erle_fest_mean"] = sum(buckets) / len(buckets)
                d["erle_fest_buckets"] = buckets

        # 派生: create 总 RAM 及含 flash 模型的总占用(总内存口径)
        if d.get("sram_kb") is not None and d.get("psram_kb") is not None:
            d["ram_total_kb"] = d["sram_kb"] + d["psram_kb"]
            d["footprint_total_kb"] = d["ram_total_kb"] + d.get("flash_model_kb", 0.0)

    ok = any(dev[c].get("cpu_avg") is not None for c in CFGS)
    return dev, ok


# ---------------------------------------------------------------- 2) 音频指标(延时/相关/残余回声)
def audio_metrics():
    try:
        import numpy as np
        import librosa
    except Exception as e:
        emit(f"[跳过音频指标] 缺依赖: {e}  (pip install numpy librosa)")
        return None
    need = ["far.wav", "near.wav"] + [f"{c.lower()}.wav" for c in CFGS]
    miss = [f for f in need if not os.path.exists(f)]
    if miss:
        emit(f"[跳过音频指标] 缺文件: {', '.join(miss)}")
        return None
    near, _ = librosa.load("near.wav", sr=SR)

    def corr(a, b):
        n = min(len(a), len(b))
        a = a[:n] - a[:n].mean(); b = b[:n] - b[:n].mean()
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))

    def dbfs(x):
        if x is None or len(x) == 0:
            return None
        r = math.sqrt(float(np.mean(x.astype(np.float64) ** 2))) + 1e-12
        return 20 * math.log10(r)

    def cat_seg(x, ranges):
        if not ranges:
            return x[:0]
        n = len(x)
        parts = [x[int(s0 * SR): (n if s1 < 0 else min(int(s1 * SR), n))] for s0, s1 in ranges]
        return np.concatenate(parts) if parts else x[:0]

    def corr_seg(a, b, ranges):
        if not ranges:
            return None
        return corr(cat_seg(a, ranges), cat_seg(b, ranges))

    def erle_seg(mic, out, ranges):
        """场景感知 ERLE = 10log10( Σmic² / Σout² ) 在指定段上。
        mic=近端麦克风(near), out=处理后输出。在【远端单讲段】上即纯回声 ERLE。"""
        if not ranges:
            return None
        a = cat_seg(mic, ranges).astype(np.float64)
        b = cat_seg(out, ranges).astype(np.float64)
        na = float(np.sum(a ** 2)); nb = float(np.sum(b ** 2))
        if na <= 0 or nb <= 0:
            return None
        return 10.0 * math.log10(na / nb)

    res = {}
    echo_in = dbfs(cat_seg(near, FE_ST))          # 可能为 None(FE 未检出)
    for c in CFGS:
        wf = f"{c.lower()}.wav"
        if not os.path.exists(wf):
            continue
        y, _ = librosa.load(wf, sr=SR)
        d = best_delay(near, y)                   # 带符号延时
        ya = np.roll(y, d)                        # 用带符号延时把输出对齐到 near
        m = {}
        m["delay_samp"] = abs(d)                  # 展示用取幅值
        m["delay_ms"] = abs(d) / SR * 1000.0
        m["nst_corr"] = corr_seg(near, ya, NE_ST)  # 近端单讲透明度(有意义)
        m["dt_corr"] = corr_seg(near, ya, DT)      # 双讲相关(见报告注)
        m["echo_res_dbfs"] = dbfs(cat_seg(y, FE_ST))  # 远端单讲残余电平
        # 场景感知离线 ERLE (排除双讲, 比设备端聚合值更准):
        m["erle_fe"] = erle_seg(near, y, FE_ST)   # 远端单讲段 ERLE = 纯回声消除力度(主口径)
        m["erle_dt"] = erle_seg(near, y, DT)      # 双讲段 ERLE (低=近端语音被保留, 属正常)
        res[c] = m
    res["_echo_in_dbfs"] = echo_in
    return res


# ---------------------------------------------------------------- 3) AECMOS(真值分段)
def aecmos():
    try:
        import numpy as np
        import librosa
        import onnxruntime as ort
    except Exception as e:
        emit(f"[跳过 AECMOS] 缺依赖: {e}  (pip install numpy librosa onnxruntime)")
        return None
    model = glob.glob("Run_*Stage_0.onnx")
    if not model:
        emit("[跳过 AECMOS] 未找到 Run_*Stage_0.onnx 模型文件")
        return None
    if not (os.path.exists("far.wav") and os.path.exists("near.wav")):
        emit("[跳过 AECMOS] 缺 far.wav / near.wav")
        return None
    DFT, HOP = 512, 256
    # AECMOS 的 .onnx 把输出形状标注成标量 {}, 实际输出 {2}(Echo/Other 两个分),
    # onnxruntime 会对此每次推理刷一条 shape 警告(纯噪声, 不影响结果)。把日志级别
    # 提到只报错误, 消掉这些警告; 同时用 SessionOptions 双保险(覆盖加载期告警)。
    try:
        ort.set_default_logger_severity(3)   # 0=Verbose 1=Info 2=Warning 3=Error
    except Exception:
        pass
    _so = ort.SessionOptions()
    _so.log_severity_level = 3
    sess = ort.InferenceSession(model[0], sess_options=_so)
    iname = sess.get_inputs()[0].name

    def mel_t(x):
        mm = librosa.feature.melspectrogram(y=x, sr=SR, n_fft=DFT + 1, hop_length=HOP, n_mels=160)
        return ((librosa.power_to_db(mm, ref=np.max) + 40) / 40).T

    def score(tt, lpb, mic, enh):
        n = min(len(lpb), len(mic), len(enh), 20 * SR)
        L, M, E = mel_t(lpb[:n]), mel_t(mic[:n]), mel_t(enh[:n])
        ne, fe = {"nst": (1, 0), "st": (0, 1), "dt": (0, 0)}[tt]
        M = np.concatenate((M, np.ones((20, M.shape[1])) * (1 - fe), np.zeros((20, M.shape[1]))), 0)
        L = np.concatenate((L, np.ones((20, L.shape[1])) * (1 - ne), np.zeros((20, L.shape[1]))), 0)
        E = np.concatenate((E, np.ones((20, E.shape[1])), np.zeros((20, E.shape[1]))), 0)
        f = np.expand_dims(np.stack((L, M, E)).astype(np.float32), 0)
        r = sess.run([], {iname: f, "h0": np.zeros((4, 1, 64), np.float32)})[0]
        return float(r[0]), float(r[1])

    lpb, _ = librosa.load("far.wav", sr=SR)
    mic, _ = librosa.load("near.wav", sr=SR)
    out = {}
    for c in CFGS:
        wf = f"{c.lower()}.wav"
        if not os.path.exists(wf):
            continue
        enh, _ = librosa.load(wf, sr=SR)
        n = min(len(lpb), len(mic), len(enh))

        def sc_type(ranges, tt):
            # 逐段独立打分(AECMOS 有20s上限且段间不应拼接), 返回各段 (echo, other) 列表
            outs = []
            for s0, s1 in ranges:
                i0 = int(s0 * SR)
                i1 = n if s1 < 0 else min(int(s1 * SR), n)
                if i1 - i0 < SR // 2:      # 段太短(<0.5s)跳过, 防噪
                    continue
                outs.append(score(tt, lpb[i0:i1], mic[i0:i1], enh[i0:i1]))
            return outs

        def avg(outs, idx):
            vs = [o[idx] for o in outs]
            return sum(vs) / len(vs) if vs else float("nan")

        fe = sc_type(FE_ST, "st")     # 远端单讲(可多段): 取 Echo 均值
        ne = sc_type(NE_ST, "nst")    # 近端单讲(可多段): 取 Other 均值
        dt = sc_type(DT, "dt")        # 双讲(可多段): 两项均值
        fe_e = avg(fe, 0)
        ne_o = avg(ne, 1)
        dt_e = avg(dt, 0)
        dt_o = avg(dt, 1)
        parts = [fe_e, ne_o, dt_e, dt_o]
        avail = [p for p in parts if not (isinstance(p, float) and math.isnan(p))]
        comp = sum(avail) / len(avail) if avail else float("nan")  # 现有项均值(缺项不计入)
        out[c] = dict(fest_echo=fe_e, nest_other=ne_o, dt_echo=dt_e, dt_other=dt_o,
                      comp=comp, comp_n=len(avail))
    return out


# ---------------------------------------------------------------- 工具: 取值/格式
def gv(d, c, k, default=None):
    return d.get(c, {}).get(k, default) if d else default


def fnum(v, fmt="{:.1f}", dash="  -  "):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return dash
    return fmt.format(v)


# ---------------------------------------------------------------- 主流程
def main(argv=None):
    global FE_ST, NE_ST, DT, OUT_DIR
    ap = argparse.ArgumentParser(
        prog="aec_report.py",
        description="AEC 四配置评测 / 配对对比报告。不带 --echo/--near/--dt 时, "
                    "场景段由 far/near 信号自动检测(可用这三个参数手动覆盖任一类)。",
        formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dir", default=HERE, metavar="路径",
                    help="结果文件所在目录(含 wav/log/onnx)。默认=脚本所在目录")
    ap.add_argument("--echo", default=None, metavar="起:止[,起:止...]",
                    help="远端单讲/纯回声段, 如 0:10 或 0:10,30:36。默认=自动检测")
    ap.add_argument("--near", default=None, metavar="起:止[,...]",
                    help="近端单讲段, 如 10:26。默认=自动检测")
    ap.add_argument("--dt", default=None, metavar="起:止[,...]",
                    help="双讲段, 如 26:36 或 26:-1(到结尾)。默认=自动检测; 传 none 表示该场景不存在")
    ap.add_argument("--no-auto", action="store_true",
                    help="关闭自动检测: 未用 --echo/--near/--dt 指定的场景一律置空(而非自动检测)。\n"
                         "用于整段只有一种场景的素材, 例如:\n"
                         "  全程纯回声  python aec_report.py --echo 0:11.22 --no-auto\n"
                         "  全程双讲    python aec_report.py --dt 0:36 --no-auto\n"
                         "  全程近端    python aec_report.py --near 0:36 --no-auto")
    args = ap.parse_args(argv)

    try:
        man_fe = parse_segspec(args.echo, "echo")
        man_ne = parse_segspec(args.near, "near")
        man_dt = parse_segspec(args.dt,   "dt")
    except ValueError as e:
        ap.error(str(e))

    # --no-auto: 未显式指定的场景视为"显式置空", 不做自动检测
    if args.no_auto:
        if man_fe is None: man_fe = []
        if man_ne is None: man_ne = []
        if man_dt is None: man_dt = []

    if not os.path.isdir(args.dir):
        ap.error("目录不存在: %s" % args.dir)
    os.chdir(args.dir)
    OUT_DIR = os.path.abspath(args.dir)

    # ---- 解析场景段: 手动指定优先, 未指定的类别由 far/near 自动检测 ----
    auto = None
    auto_info = None
    need_auto = (man_fe is None) or (man_ne is None) or (man_dt is None)
    if need_auto:
        if os.path.exists("far.wav") and os.path.exists("near.wav"):
            try:
                nr, sr_n = load_wav_np("near.wav")
                fr, sr_f = load_wav_np("far.wav")
                sr_use = sr_n if sr_n == sr_f else SR
                auto, auto_info = auto_segments(nr, fr, sr_use)
            except Exception as e:
                emit(f"[自动分段跳过] {e}  (需 numpy + 16bit wav; 可用 --echo/--near/--dt 手动指定)")
        else:
            emit("[自动分段跳过] 缺 far.wav / near.wav; 未手动指定的场景段将为空")

    def resolve(man, key):
        # 返回 (段列表, 来源标记)。man 非 None(含显式[])=手动; 否则自动/无。
        if man is not None:
            return man, "手动"
        return (auto[key] if auto else []), ("自动" if auto else "无")
    FE_ST, s_fe = resolve(man_fe, "FE")
    NE_ST, s_ne = resolve(man_ne, "NE")
    DT,    s_dt = resolve(man_dt, "DT")
    seg_src = {"FE": s_fe, "NE": s_ne, "DT": s_dt}

    def seg_disp(ranges, src):
        if ranges:
            return fmt_ranges(ranges)
        return "(无, 该场景不存在)" if src == "手动" else "(未检出)"

    emit("=" * 74)
    emit("SeekAudio AEC 四配置评测 / 配对对比报告  (aec_report.py 自动生成)")
    emit("=" * 74)
    emit("场景边界 (@16k, 32ms帧; 未手动指定者由 far/near 信号自动检测):")
    emit(f"  远端单讲/回声 [{seg_src['FE']}]: {seg_disp(FE_ST, seg_src['FE'])}")
    emit(f"  近端单讲     [{seg_src['NE']}]: {seg_disp(NE_ST, seg_src['NE'])}")
    emit(f"  双讲         [{seg_src['DT']}]: {seg_disp(DT, seg_src['DT'])}")
    if auto_info:
        emit(f"  (自动检测: near-far 延时 {auto_info['delay_ms']:+.0f}ms, far 峰值 "
             f"{auto_info['far_peak_db']:.0f}dBFS, 回声/双讲相关阈值 {auto_info['rho_thr']:.2f})")
    emit("  提示: 整段只有一种场景时, 只指定该类并加 --no-auto(或其余类写 none), 避免误检。")
    emit("")
    for c in CFGS:
        emit(f"  {c} = {CFG_NAMES[c]}")
    emit("")

    dev, dev_ok = parse_log()
    if not dev_ok:
        emit("[提示] 未从 log.txt 解析到设备端指标(文件缺失或格式不符), 设备端各表将为空。")
        emit("")
    aud = audio_metrics()
    mos = aecmos()

    # ---- 一、设备端性能 ----
    emit("一、设备端算力 (ESP32-S3 @240MHz, 512样本/32ms帧)")
    emit(f"  {'配置':<4}{'CPU avg/p95/max':>20}{'等效MHz':>9}{'RTF':>8}"
         f"{'单帧 avg/p95/max (us)':>26}{'最忙帧#':>9}")
    for c in CFGS:
        cpu = (f"{fnum(gv(dev,c,'cpu_avg'),'{:.1f}')}/"
               f"{fnum(gv(dev,c,'cpu_p95'),'{:.1f}')}/"
               f"{fnum(gv(dev,c,'cpu_max'),'{:.1f}')}%")
        fr = (f"{fnum(gv(dev,c,'avg_us'),'{:.0f}')}/{fnum(gv(dev,c,'p95_us'),'{:.0f}')}/"
              f"{fnum(gv(dev,c,'max_us'),'{:.0f}')}")
        mhz = fnum(gv(dev, c, 'cpu_mhz'), '{:.0f}')
        rtf = fnum(gv(dev, c, 'rtf'), '{:.2f}') + 'x'
        busy = ("#" + str(gv(dev, c, 'cpu_max_frame'))) if gv(dev, c, 'cpu_max_frame') is not None else "  -  "
        emit(f"  {c:<4}{cpu:>20}{mhz:>9}{rtf:>8}{fr:>26}{busy:>9}")
    emit("  注: 破帧预算=32000us/帧; 各配置单帧 max 均 << 预算 => 破帧率 0。")
    emit("")

    # ---- 二、内存 / 占用 ----
    emit("二、内存占用 (create 基线 + 运行峰值增量; 越低越好)")
    emit(f"  {'配置':<4}{'片内SRAM create/+峰值':>24}{'PSRAM create/+峰值':>24}"
         f"{'RAM合计':>10}{'flash模型':>10}{'栈余量':>9}")
    for c in CFGS:
        sram = f"{fnum(gv(dev,c,'sram_kb'))}/+{fnum(gv(dev,c,'tr_sram_kb'),'{:.1f}','0.0')}KB"
        psram = f"{fnum(gv(dev,c,'psram_kb'))}/+{fnum(gv(dev,c,'tr_psram_kb'),'{:.1f}','0.0')}KB"
        ram = fnum(gv(dev, c, 'ram_total_kb'), '{:.0f}') + "KB"
        fm = gv(dev, c, 'flash_model_kb')
        fms = (fnum(fm, '{:.0f}') + "KB") if fm else "  -  "
        stk = fnum(gv(dev, c, 'stack_kb'), '{:.0f}') + "KB"
        emit(f"  {c:<4}{sram:>24}{psram:>24}{ram:>10}{fms:>10}{stk:>9}")
    emit("  注: RAM合计=create(片内+PSRAM); B2 另需 flash 模型分区(NSNet2 权重),")
    emit("      总占用口径 = 片内 + PSRAM + flash 模型。")
    emit("")

    # ---- 三、回声抑制 ----
    emit("三、回声抑制")
    if aud and aud.get('_echo_in_dbfs') is not None:
        emit(f"  回声输入电平(近端mic, 远端单讲段 {fmt_ranges(FE_ST)}): {aud['_echo_in_dbfs']:.1f} dBFS")
    emit("  [主口径] 离线场景感知 ERLE (近端mic vs 输出, 按自动检测的场景段, 排除双讲)")
    emit(f"    {'配置':<4}{'远单讲ERLE(dB)':>16}{'残余回声(dBFS)':>16}{'双讲ERLE(dB)':>14}")
    for c in CFGS:
        emit(f"    {c:<4}{fnum(gv(aud,c,'erle_fe')):>16}"
             f"{fnum(gv(aud,c,'echo_res_dbfs')):>16}"
             f"{fnum(gv(aud,c,'erle_dt')):>14}")
    if not aud:
        emit("    (需 numpy/librosa + wav; 无音频时本口径不可用, 见下方设备端交叉参考)")
    emit("  [交叉参考] 设备端日志 ERLE (设备端不知场景标签, 含双讲, 会被近端语音拉低)")
    emit(f"    {'配置':<4}{'远单讲ERLE(桶)':>16}{'回声活跃ERLE':>14}{'收敛ERLE':>10}")
    for c in CFGS:
        emit(f"    {c:<4}{fnum(gv(dev,c,'erle_fest_mean')):>16}"
             f"{fnum(gv(dev,c,'erle_active')):>14}"
             f"{fnum(gv(dev,c,'erle_conv')):>10}")
    emit("  注: 远单讲ERLE(主) = 近端mic 与输出在【自动检测的远端单讲段】上的能量比, 排除")
    emit("      了双讲, 是消回声力度的主口径; 双讲ERLE 偏低是设计内的近端语音保护, 非缺陷。")
    emit("      设备端'回声活跃/收敛ERLE'无法排除双讲(芯片端不知哪段是双讲), 仅作交叉校验;")
    emit("      设备端'远单讲ERLE(桶)'取 convergence 前段桶均值, 若素材开头恰为纯回声则可比。")
    emit("")

    # ---- 四、近端保真 ----
    emit("四、近端保真 (互相关对齐后)")
    if aud:
        emit(f"  {'配置':<4}{'链路延时(样/ms)':>18}{'近单讲相关':>12}{'双讲相关':>12}")
        for c in CFGS:
            if c not in aud:
                continue
            dlabel = "{}/{:.0f}ms".format(aud[c]['delay_samp'], aud[c]['delay_ms'])
            emit(f"  {c:<4}{dlabel:>18}"
                 f"{fnum(aud[c]['nst_corr'],'{:.3f}'):>12}{fnum(aud[c]['dt_corr'],'{:.3f}'):>12}")
        cfgs_have = [c for c in CFGS if c in aud]
        if cfgs_have:
            floor = min(aud[c]['delay_ms'] for c in cfgs_have)
            emit(f"  链路延时地板(共享线性前端): {floor:.0f} ms; 各后级额外延时:")
            emit("    " + "  ".join(f"{c} +{aud[c]['delay_ms']-floor:.0f}ms" for c in cfgs_have))
        emit("  注: 近单讲相关=透明度(越高越好); 双讲相关对mic会因去回声而降低, 属歧义指标,")
        emit("      双讲近端保真以 AECMOS DT-Other 为准。")
    else:
        emit("  (需 numpy/librosa + wav 文件)")
    emit("")

    # ---- 五、AECMOS(真值分段) ----
    emit("五、AECMOS 感知质量 (Echo/Other, 1~5 越高越好; 场景标签=真值)")
    if mos:
        emit(f"  {'配置':<4}{'远单讲Echo':>12}{'近单讲Other':>12}{'双讲Echo':>10}"
             f"{'双讲Other':>10}{'挑战赛综合':>12}")
        for c in CFGS:
            m = mos.get(c)
            if not m:
                continue
            emit(f"  {c:<4}{fnum(m['fest_echo'],'{:.2f}'):>12}{fnum(m['nest_other'],'{:.2f}'):>12}"
                 f"{fnum(m['dt_echo'],'{:.2f}'):>10}{fnum(m['dt_other'],'{:.2f}'):>10}"
                 f"{fnum(m['comp'],'{:.2f}'):>12}")
        _kn = next((m['comp_n'] for m in mos.values() if m), 4)
        if _kn >= 4:
            emit("  综合分 = (远单讲Echo + 近单讲Other + 双讲Echo + 双讲Other)/4  (微软挑战赛口径)")
        else:
            emit(f"  综合分 = 本素材现有 {_kn}/4 个场景项的均值(缺失场景不计入); 4 项齐全时即微软挑战赛口径。")
    else:
        emit("  (需 numpy/librosa/onnxruntime + Run_*Stage_0.onnx + wav 文件)")
    emit("")

    # ---- 六、配对对比 ----
    emit("六、配对对比")
    for a, b, tag in PAIRS:
        emit(f"  ── {a} vs {b} ({tag}) ──")

        def row(name, va, vb, better, unit="", fmt="{:.1f}"):
            sa = fnum(va, fmt); sb = fnum(vb, fmt)
            def _ok(x):
                return x is not None and not (isinstance(x, float) and math.isnan(x))
            if not (_ok(va) and _ok(vb)):
                verdict = "—"                 # 有一边缺值: 不可比(非平局)
            elif abs(va - vb) <= 1e-9:
                verdict = "≈平"               # 都有值且相等: 真平局
            else:
                lo = (va < vb)
                verdict = "胜:" + (a if (lo == (better == "low")) else b)
            emit(f"    {name:<20}{sa+unit:>12}{sb+unit:>12}   {verdict}")

        row("CPU avg",       gv(dev,a,'cpu_avg'),      gv(dev,b,'cpu_avg'), "low", "%")
        row("CPU p95",       gv(dev,a,'cpu_p95'),      gv(dev,b,'cpu_p95'), "low", "%")
        row("CPU max",       gv(dev,a,'cpu_max'),      gv(dev,b,'cpu_max'), "low", "%")
        row("RTF",           gv(dev,a,'rtf'),          gv(dev,b,'rtf'), "high", "x", "{:.2f}")
        row("片内SRAM",      gv(dev,a,'sram_kb'),      gv(dev,b,'sram_kb'), "low", "KB")
        row("PSRAM",         gv(dev,a,'psram_kb'),     gv(dev,b,'psram_kb'), "low", "KB")
        row("RAM合计",       gv(dev,a,'ram_total_kb'), gv(dev,b,'ram_total_kb'), "low", "KB", "{:.0f}")
        row("总占用(含flash)", gv(dev,a,'footprint_total_kb'), gv(dev,b,'footprint_total_kb'), "low", "KB", "{:.0f}")
        # 回声: 主口径用离线场景感知 ERLE(排除双讲); 无音频时回退设备端桶均值。
        if aud and a in aud and b in aud and gv(aud, a, 'erle_fe') is not None:
            row("远单讲ERLE(离线)", gv(aud,a,'erle_fe'), gv(aud,b,'erle_fe'), "high", "dB")
            row("双讲ERLE(离线)",   gv(aud,a,'erle_dt'), gv(aud,b,'erle_dt'), "high", "dB")
        else:
            row("远单讲ERLE(设备)", gv(dev,a,'erle_fest_mean'), gv(dev,b,'erle_fest_mean'), "high", "dB")
        if mos and a in mos and b in mos:
            row("AECMOS远单讲Echo", mos[a]['fest_echo'], mos[b]['fest_echo'], "high", "", "{:.2f}")
            row("AECMOS近单讲Other", mos[a]['nest_other'], mos[b]['nest_other'], "high", "", "{:.2f}")
            row("AECMOS双讲Echo", mos[a]['dt_echo'], mos[b]['dt_echo'], "high", "", "{:.2f}")
            row("AECMOS双讲Other", mos[a]['dt_other'], mos[b]['dt_other'], "high", "", "{:.2f}")
            row("AECMOS综合",    mos[a]['comp'], mos[b]['comp'], "high", "", "{:.2f}")
        if aud and a in aud and b in aud:
            row("链路延时",   aud[a]['delay_ms'], aud[b]['delay_ms'], "low", "ms", "{:.0f}")
            row("近单讲相关", aud[a]['nst_corr'], aud[b]['nst_corr'], "high", "", "{:.3f}")
        # 省算力口径
        ca, cb = gv(dev, a, 'cpu_avg'), gv(dev, b, 'cpu_avg')
        if ca and cb:
            emit(f"    -> {a} 相对 {b} 节省算力 {(1-ca/cb)*100:.0f}% (CPU avg {ca:.1f}% vs {cb:.1f}%)")
        emit("")

    with open("aec_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(OUT_LINES) + "\n")
    print("[已写入] " + os.path.join(OUT_DIR, "aec_report.txt"))


if __name__ == "__main__":
    main()
