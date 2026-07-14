#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
aec_report.py -- AEC four-config evaluation / paired-comparison report
                 (updated for the new seekaudio_aec_test output format)

=============================== USAGE ===============================
[Mode 1] Zero arguments (simplest): put this script in the same folder as the
    result files and run:
        python aec_report.py
    Files needed: far.wav near.wav a1.wav a2.wav b1.wav b2.wav  log.txt
                  Run_*Stage_0.onnx (AECMOS model; that section is skipped if
                  absent)
    Scene boundaries (which part is echo / near-end / double-talk) are NOT
    hard-coded; they are auto-detected from the far.wav / near.wav signals (see
    auto_segments), so the tool adapts to any material. The detected boundaries
    are printed in the report header for you to verify.

[Mode 2] Manually specify the scene segments (overrides auto-detection): use
    --echo / --near / --dt to give the time ranges.
        python aec_report.py --echo 0:10 --near 10:26 --dt 26:36
        python aec_report.py --echo 0:8,30:36 --dt 26:-1
    - --echo : far-end single-talk / pure-echo segment (scores Echo MOS only)
    - --near : near-end single-talk segment          (scores Other MOS only)
    - --dt   : double-talk segment                   (scores both Echo & Other)
    - Format "start:end" (seconds); a category may have several segments,
      comma-separated (e.g. 0:8,30:36); use -1 as end for "to end" (e.g. 26:-1).
    - Partial override supported: give only one or two; the omitted categories
      still use auto-detection.
      e.g. python aec_report.py --dt 26:-1  => echo/near auto, dt as given.
    - Clip with only one scenario (all far single-talk / all double-talk / all
      near-end): give just that category and add --no-auto to disable
      auto-detection of the others (otherwise they get mis-detected):
        all far single-talk  python aec_report.py --echo 0:11.22 --no-auto
        all double-talk      python aec_report.py --dt 0:36 --no-auto
        all near single-talk python aec_report.py --near 0:36 --no-auto
      Or set a category to 'none' explicitly: --echo 0:8 --near none --dt 8:11

[Mode 3] Point at the result directory when files are not in the script folder:
        python aec_report.py --dir D:\out
        python aec_report.py --dir D:\out --echo 0:8,30:36 --dt 26:-1
=====================================================================

Results are printed to the screen and also written to <dir>/aec_report_en.txt.
Dependencies: auto-segmentation needs only numpy (+ wav); the audio / AECMOS
    sections additionally need librosa / onnxruntime.
      pip install numpy librosa onnxruntime
      (With deps missing, device-log parsing still runs; with no numpy/wav,
       auto-segmentation is skipped -- then give --echo/--near/--dt manually,
       or just read the device-side tables.)
Full argument reference: python aec_report.py --help

-- Changes vs. the previous version (seekaudio_aec_test code/output changed) --
  * A1/A2 now go through the sunk public API (seekaudio_aec_create, 2 args);
    create() memory includes the in-library AFE front-end. B1/B2 are still the
    esp-sr baselines. Metrics are black-box observations, unaffected by this.
  * CPU load line adds max% + frame idx: "26.2% avg / 29.4% p95 / 32.1% max
    (frame #11)".
  * per-frame max line adds "at frame #N/total".
  * New lines: "ERLE converged" (last quarter, echo-active) and "run transient"
    (peak memory during the run).
  * B2's NSNet2 weights occupy a flash model partition (MODEL_LOADER line),
    counted into the total footprint.
  * Scene boundaries are now auto-detected from the signals; the old defaults
    hard-coded to one clip have been dropped.
"""
# ---- Scene boundaries ----------------------------------------------------
# No hard-coded time ranges (those only hold for one clip). When arguments are
# empty, auto_segments() detects them from the far/near signals; override any
# category with --echo/--near/--dt.
# Each category is a "segment list": one segment 0:10, two 0:10,30:36; -1 = end.
FE_ST, NE_ST, DT = [], [], []   # filled by main (auto-detected or manual)

# ---- Auto-segmentation tunables (rarely need changing) -------------------
SEG_WIN_MS      = 32     # analysis frame length (ms)
SEG_FAR_ABS_DB  = -50.0  # far absolute activity gate (dBFS): below => speaker silent (no echo)
SEG_NEAR_ABS_DB = -50.0  # near absolute activity gate (dBFS)
SEG_FAR_REL_DB  = 20.0   # far relative-to-peak gate (dB): >20 dB below far peak => inactive
SEG_MED_FRAMES  = 5      # label median/mode filter window (frames, de-flicker)
SEG_MIN_DUR     = 0.5    # minimum segment length (s); shorter fragments dropped
SEG_BRIDGE      = 0.30   # same-label segments closer than this (s) are bridged
SEG_RHO_THR     = None   # echo/doubletalk correlation threshold; None = Otsu adaptive (recommended)

# Pairs: A1 vs B1 (traditional NS vs traditional NS), A2 vs B2 (AI NR vs AI NR)
PAIRS = [("A1", "B1", "traditional NS vs traditional NS"),
         ("A2", "B2", "AI NR vs AI NR")]

# Full config names (for the legend; match the device-side backend names)
CFG_NAMES = {
    "A1": "SeekAudio AEC + NLP + WebRTC NS",
    "A2": "SeekAudio AEC + NLP + AI Noise",
    "B1": "FD-AEC + NLP + ns_pro   (esp-sr baseline)",
    "B2": "FD-AEC + NLP + NSNet2   (esp-sr baseline)",
}

import os, re, sys, glob, math, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 16000
CFGS = ["A1", "A2", "B1", "B2"]
OUT_LINES = []
OUT_DIR = HERE   # replaced by main with the actual result directory


# ---------------------------------------------------------------- 0) auto-segmentation
def load_wav_np(path):
    """Read a 16-bit PCM wav with stdlib wave + numpy -> (float[-1,1], sr).
    Needs only numpy (no librosa); used by auto-segmentation. Multichannel ->
    first channel."""
    import wave
    import numpy as np
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        n = w.getnframes()
        raw = w.readframes(n)
    if sw != 2:
        raise ValueError(f"{path}: only 16-bit PCM supported (got {sw*8}-bit)")
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
    """Otsu two-class split of a 1-D array; returns threshold, or None if data
    is degenerate."""
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
    """Signed delay of near vs far (samples) via the FFT cross-correlation peak."""
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
    """Detect scene segments from far (loudspeaker ref) / near (mic). Returns
    (segs_dict, info). segs_dict = {'FE':[(s,e)..],'NE':[..],'DT':[..]}.

    Criteria (per 32 ms frame):
      * far active = absolute dBFS gate AND relative-to-far-peak gate
                     -> is echo present (speaker playing)
      * near active = absolute dBFS gate
      * within far-active frames, use the normalized correlation rho between
        near and delay-aligned far + an Otsu threshold:
          rho high -> near ~ echo (pure echo, FE); rho low -> uncorrelated
          near speech present (double-talk, DT)
      * far inactive AND near active -> near single-talk (NE); both inactive ->
        silence (ignored)
    Labels are mode-filtered to de-flicker, adjacent same-label segments merged,
    small gaps bridged, over-short segments dropped."""
    import numpy as np
    win = int(round(SEG_WIN_MS / 1000.0 * sr))
    d = best_delay(near, far)
    far_al = np.roll(far, d)
    n = min(len(near), len(far_al))
    near = near[:n].astype(np.float64)
    far_al = far_al[:n].astype(np.float64)
    nf = n // win
    if nf < 2:
        return {"FE": [], "NE": [], "DT": []}, {"delay": d, "note": "audio too short"}

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

    # mode filter to de-flicker
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
    """Parse '0:10' or '0:10,30:36' into [(0.0,10.0),...]; -1 means to end.
    Returns: None = not provided (auto-detect); [] = explicitly empty (none/-,
    that scenario does not exist); non-empty list = manually specified segments."""
    if spec is None:
        return None
    s = str(spec).strip().lower()
    if s in ("none", "-", "empty", "na", ""):
        return []            # explicitly empty: scenario absent, do not auto-detect
    out = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError("--%s segment '%s' must be start:end (e.g. 0:10), or 'none' if absent" % (name, part))
        a, b = part.split(":", 1)
        try:
            a, b = float(a), float(b)
        except ValueError:
            raise ValueError("--%s segment '%s' start/end must be numbers" % (name, part))
        out.append((a, b))
    return out


def emit(s=""):
    print(s)
    OUT_LINES.append(s)


def fmt_ranges(ranges):
    return ",".join(("{:g}-{:g}s".format(a, b) if b >= 0 else "{:g}-ends".format(a))
                    for a, b in ranges)


# ---------------------------------------------------------------- 1) parse device log
def parse_log(path="log.txt"):
    """Extract device-side metrics per config block from the serial log. Pure
    stdlib, no deps. Adapted to the new aec_runner output: CPU max+frame idx /
    ERLE converged / run transient / per-frame max frame idx / B2 flash model
    partition."""
    dev = {c: {} for c in CFGS}
    if not os.path.exists(path):
        return dev, False
    txt = open(path, encoding="utf-8", errors="replace").read()

    # B2's NSNet2 weights occupy a flash model partition (global line, appears
    # before B2); counted into B2's total footprint.
    mp = re.search(r"MODEL_LOADER:\s*The partition size is\s*(\d+)\s*KB", txt)
    if mp:
        dev["B2"]["flash_model_kb"] = float(mp.group(1))

    # Split on the device stats separator "-------- A1: ... --------" (>=4 dashes,
    # so the "====" section headers and the '+' inside names are avoided). Other
    # blocks such as SA-FULL do not match and are ignored.
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

        # per-frame max now carries a frame idx: "10287.0 us  at frame #11/1148"
        mx = re.search(r"per-frame max\s*:\s*([\d.]+)\s*us(?:\s+at frame #(\d+)/(\d+))?", blk)
        if mx:
            d["max_us"] = float(mx.group(1))
            if mx.group(2):
                d["max_frame"] = int(mx.group(2))
                d["total_frames"] = int(mx.group(3))

        # CPU load now carries max% + frame idx:
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
        d["erle_conv"]     = g(r"ERLE converged\s*:\s*([-\d.]+)\s*dB")   # new line

        # create(): wall clock + internal SRAM / PSRAM
        cr = re.search(r"create\(\)\s*:\s*([\d.]+)\s*ms;\s*internal SRAM\s*([\d.]+)"
                       r"\s*KB,\s*PSRAM\s*([\d.]+)\s*KB", blk)
        if cr:
            d["create_ms"] = float(cr.group(1))
            d["sram_kb"]   = float(cr.group(2))
            d["psram_kb"]  = float(cr.group(3))

        # run transient: peak increment over the create baseline during the run
        rt = re.search(r"run transient\s*:\s*internal SRAM peak \+([\d.]+)\s*KB,"
                       r"\s*PSRAM peak \+([\d.]+)\s*KB", blk)
        if rt:
            d["tr_sram_kb"]  = float(rt.group(1))
            d["tr_psram_kb"] = float(rt.group(2))

        d["stack_kb"] = g(r"stack headroom\s*:\s*([\d.]+)\s*KB")
        d["crc32"] = (re.search(r"output CRC32\s*:\s*(0x[0-9A-Fa-f]+)", blk) or [None, None])[1]

        # far single-talk ERLE: the numeric buckets before the first "--" on the
        # convergence line (pure-echo region, no double-talk contamination).
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

        # derived: create total RAM, and total footprint incl. flash model
        if d.get("sram_kb") is not None and d.get("psram_kb") is not None:
            d["ram_total_kb"] = d["sram_kb"] + d["psram_kb"]
            d["footprint_total_kb"] = d["ram_total_kb"] + d.get("flash_model_kb", 0.0)

    ok = any(dev[c].get("cpu_avg") is not None for c in CFGS)
    return dev, ok


# ---------------------------------------------------------------- 2) audio metrics (delay/corr/residual echo)
def audio_metrics():
    try:
        import numpy as np
        import librosa
    except Exception as e:
        emit(f"[skip audio metrics] missing deps: {e}  (pip install numpy librosa)")
        return None
    need = ["far.wav", "near.wav"] + [f"{c.lower()}.wav" for c in CFGS]
    miss = [f for f in need if not os.path.exists(f)]
    if miss:
        emit(f"[skip audio metrics] missing files: {', '.join(miss)}")
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
        """Scene-aware ERLE = 10log10( sum(mic^2) / sum(out^2) ) over the given
        segments. mic = near microphone, out = processed output. Over the
        far single-talk segment this is the pure-echo ERLE."""
        if not ranges:
            return None
        a = cat_seg(mic, ranges).astype(np.float64)
        b = cat_seg(out, ranges).astype(np.float64)
        na = float(np.sum(a ** 2)); nb = float(np.sum(b ** 2))
        if na <= 0 or nb <= 0:
            return None
        return 10.0 * math.log10(na / nb)

    res = {}
    echo_in = dbfs(cat_seg(near, FE_ST))          # may be None (FE not detected)
    for c in CFGS:
        wf = f"{c.lower()}.wav"
        if not os.path.exists(wf):
            continue
        y, _ = librosa.load(wf, sr=SR)
        d = best_delay(near, y)                   # signed delay
        ya = np.roll(y, d)                        # align output to near with the signed delay
        m = {}
        m["delay_samp"] = abs(d)                  # magnitude for display
        m["delay_ms"] = abs(d) / SR * 1000.0
        m["nst_corr"] = corr_seg(near, ya, NE_ST)  # near single-talk transparency (meaningful)
        m["dt_corr"] = corr_seg(near, ya, DT)      # double-talk correlation (see report note)
        m["echo_res_dbfs"] = dbfs(cat_seg(y, FE_ST))  # far single-talk residual level
        # scene-aware offline ERLE (excludes double-talk; more accurate than the device aggregate):
        m["erle_fe"] = erle_seg(near, y, FE_ST)   # far single-talk ERLE = pure echo cancellation (primary)
        m["erle_dt"] = erle_seg(near, y, DT)      # double-talk ERLE (low = near speech preserved, normal)
        res[c] = m
    res["_echo_in_dbfs"] = echo_in
    return res


# ---------------------------------------------------------------- 3) AECMOS (ground-truth segments)
def aecmos():
    try:
        import numpy as np
        import librosa
        import onnxruntime as ort
    except Exception as e:
        emit(f"[skip AECMOS] missing deps: {e}  (pip install numpy librosa onnxruntime)")
        return None
    model = glob.glob("Run_*Stage_0.onnx")
    if not model:
        emit("[skip AECMOS] Run_*Stage_0.onnx model file not found")
        return None
    if not (os.path.exists("far.wav") and os.path.exists("near.wav")):
        emit("[skip AECMOS] missing far.wav / near.wav")
        return None
    DFT, HOP = 512, 256
    # The AECMOS .onnx declares its output shape as scalar {} but actually emits
    # {2} (the Echo/Other scores), so onnxruntime prints a shape warning on every
    # inference (pure noise, results unaffected). Raise the log level to errors
    # only to silence them; use SessionOptions as a second guard (covers the
    # load-time warning).
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
            # score each segment independently (AECMOS has a 20 s cap and segments
            # must not be concatenated); return a list of (echo, other) per segment
            outs = []
            for s0, s1 in ranges:
                i0 = int(s0 * SR)
                i1 = n if s1 < 0 else min(int(s1 * SR), n)
                if i1 - i0 < SR // 2:      # segment too short (<0.5 s): skip, anti-noise
                    continue
                outs.append(score(tt, lpb[i0:i1], mic[i0:i1], enh[i0:i1]))
            return outs

        def avg(outs, idx):
            vs = [o[idx] for o in outs]
            return sum(vs) / len(vs) if vs else float("nan")

        fe = sc_type(FE_ST, "st")     # far single-talk (may be multi-seg): mean Echo
        ne = sc_type(NE_ST, "nst")    # near single-talk (may be multi-seg): mean Other
        dt = sc_type(DT, "dt")        # double-talk (may be multi-seg): mean of both
        fe_e = avg(fe, 0)
        ne_o = avg(ne, 1)
        dt_e = avg(dt, 0)
        dt_o = avg(dt, 1)
        parts = [fe_e, ne_o, dt_e, dt_o]
        avail = [p for p in parts if not (isinstance(p, float) and math.isnan(p))]
        comp = sum(avail) / len(avail) if avail else float("nan")  # mean of available items (missing excluded)
        out[c] = dict(fest_echo=fe_e, nest_other=ne_o, dt_echo=dt_e, dt_other=dt_o,
                      comp=comp, comp_n=len(avail))
    return out


# ---------------------------------------------------------------- helpers: fetch/format
def gv(d, c, k, default=None):
    return d.get(c, {}).get(k, default) if d else default


def fnum(v, fmt="{:.1f}", dash="  -  "):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return dash
    return fmt.format(v)


# ---------------------------------------------------------------- main
def main(argv=None):
    global FE_ST, NE_ST, DT, OUT_DIR
    ap = argparse.ArgumentParser(
        prog="aec_report.py",
        description="AEC four-config evaluation / paired comparison. Without "
                    "--echo/--near/--dt, scene segments are auto-detected from "
                    "the far/near signals (override any category with those three).",
        formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dir", default=HERE, metavar="PATH",
                    help="directory holding the result files (wav/log/onnx). Default = script dir")
    ap.add_argument("--echo", default=None, metavar="start:end[,start:end...]",
                    help="far single-talk / pure-echo segment, e.g. 0:10 or 0:10,30:36. Default = auto-detect")
    ap.add_argument("--near", default=None, metavar="start:end[,...]",
                    help="near single-talk segment, e.g. 10:26. Default = auto-detect")
    ap.add_argument("--dt", default=None, metavar="start:end[,...]",
                    help="double-talk segment, e.g. 26:36 or 26:-1 (to end). Default = auto-detect; pass 'none' if absent")
    ap.add_argument("--no-auto", action="store_true",
                    help="disable auto-detection: any category not given via --echo/--near/--dt is left empty (not auto-detected).\n"
                         "For clips that contain only one scenario, e.g.:\n"
                         "  all far single-talk  python aec_report.py --echo 0:11.22 --no-auto\n"
                         "  all double-talk      python aec_report.py --dt 0:36 --no-auto\n"
                         "  all near single-talk python aec_report.py --near 0:36 --no-auto")
    args = ap.parse_args(argv)

    try:
        man_fe = parse_segspec(args.echo, "echo")
        man_ne = parse_segspec(args.near, "near")
        man_dt = parse_segspec(args.dt,   "dt")
    except ValueError as e:
        ap.error(str(e))

    # --no-auto: categories not explicitly given are treated as explicitly empty (no auto-detect)
    if args.no_auto:
        if man_fe is None: man_fe = []
        if man_ne is None: man_ne = []
        if man_dt is None: man_dt = []

    if not os.path.isdir(args.dir):
        ap.error("directory not found: %s" % args.dir)
    os.chdir(args.dir)
    OUT_DIR = os.path.abspath(args.dir)

    # ---- resolve scene segments: manual wins; unspecified categories auto-detected from far/near ----
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
                emit(f"[auto-seg skipped] {e}  (needs numpy + 16-bit wav; or give --echo/--near/--dt manually)")
        else:
            emit("[auto-seg skipped] missing far.wav / near.wav; unspecified scene segments will be empty")

    def resolve(man, key):
        # returns (segment list, source tag). man not None (incl. explicit []) = manual; else auto/none.
        if man is not None:
            return man, "manual"
        return (auto[key] if auto else []), ("auto" if auto else "none")
    FE_ST, s_fe = resolve(man_fe, "FE")
    NE_ST, s_ne = resolve(man_ne, "NE")
    DT,    s_dt = resolve(man_dt, "DT")
    seg_src = {"FE": s_fe, "NE": s_ne, "DT": s_dt}

    def seg_disp(ranges, src):
        if ranges:
            return fmt_ranges(ranges)
        return "(none, scenario absent)" if src == "manual" else "(not detected)"

    emit("=" * 74)
    emit("SeekAudio AEC four-config evaluation / paired comparison  (auto-generated by aec_report.py)")
    emit("=" * 74)
    emit("Scene boundaries (@16k, 32ms frames; categories not given manually are auto-detected from far/near):")
    emit(f"  far single-talk/echo [{seg_src['FE']}]: {seg_disp(FE_ST, seg_src['FE'])}")
    emit(f"  near single-talk     [{seg_src['NE']}]: {seg_disp(NE_ST, seg_src['NE'])}")
    emit(f"  double-talk          [{seg_src['DT']}]: {seg_disp(DT, seg_src['DT'])}")
    if auto_info:
        emit(f"  (auto-detect: near-far delay {auto_info['delay_ms']:+.0f}ms, far peak "
             f"{auto_info['far_peak_db']:.0f}dBFS, echo/doubletalk corr threshold {auto_info['rho_thr']:.2f})")
    emit("  Tip: for a clip with only one scenario, give just that category and add --no-auto (or set the others to 'none') to avoid mis-detection.")
    emit("")
    for c in CFGS:
        emit(f"  {c} = {CFG_NAMES[c]}")
    emit("")

    dev, dev_ok = parse_log()
    if not dev_ok:
        emit("[note] No device metrics parsed from log.txt (missing or format mismatch); device tables will be empty.")
        emit("")
    aud = audio_metrics()
    mos = aecmos()

    # ---- I. Device-side compute ----
    emit("I. Device-side compute (ESP32-S3 @240MHz, 512 samples / 32ms frame)")
    emit(f"  {'Cfg':<4}{'CPU avg/p95/max':>20}{'eff.MHz':>9}{'RTF':>8}"
         f"{'per-frame avg/p95/max(us)':>26}{'busiest#':>9}")
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
    emit("  Note: frame budget = 32000 us/frame; every config's per-frame max << budget => frame-miss rate 0.")
    emit("")

    # ---- II. Memory / footprint ----
    emit("II. Memory footprint (create baseline + run peak increment; lower is better)")
    emit(f"  {'Cfg':<4}{'internal SRAM cr/+pk':>24}{'PSRAM cr/+pk':>24}"
         f"{'RAM total':>10}{'flash mdl':>10}{'stack':>9}")
    for c in CFGS:
        sram = f"{fnum(gv(dev,c,'sram_kb'))}/+{fnum(gv(dev,c,'tr_sram_kb'),'{:.1f}','0.0')}KB"
        psram = f"{fnum(gv(dev,c,'psram_kb'))}/+{fnum(gv(dev,c,'tr_psram_kb'),'{:.1f}','0.0')}KB"
        ram = fnum(gv(dev, c, 'ram_total_kb'), '{:.0f}') + "KB"
        fm = gv(dev, c, 'flash_model_kb')
        fms = (fnum(fm, '{:.0f}') + "KB") if fm else "  -  "
        stk = fnum(gv(dev, c, 'stack_kb'), '{:.0f}') + "KB"
        emit(f"  {c:<4}{sram:>24}{psram:>24}{ram:>10}{fms:>10}{stk:>9}")
    emit("  Note: RAM total = create (internal + PSRAM); B2 also needs a flash model partition (NSNet2 weights),")
    emit("        so total footprint = internal + PSRAM + flash model.")
    emit("")

    # ---- III. Echo suppression ----
    emit("III. Echo suppression")
    if aud and aud.get('_echo_in_dbfs') is not None:
        emit(f"  Echo input level (near mic, far single-talk {fmt_ranges(FE_ST)}): {aud['_echo_in_dbfs']:.1f} dBFS")
    emit("  [primary] offline scene-aware ERLE (near mic vs output, per detected segment, double-talk excluded)")
    emit(f"    {'Cfg':<4}{'FE-ST ERLE(dB)':>16}{'resid echo(dBFS)':>18}{'DT ERLE(dB)':>14}")
    for c in CFGS:
        emit(f"    {c:<4}{fnum(gv(aud,c,'erle_fe')):>16}"
             f"{fnum(gv(aud,c,'echo_res_dbfs')):>18}"
             f"{fnum(gv(aud,c,'erle_dt')):>14}")
    if not aud:
        emit("    (needs numpy/librosa + wav; unavailable without audio, see device cross-check below)")
    emit("  [cross-check] device-log ERLE (device has no scene labels; includes double-talk, pulled down by near speech)")
    emit(f"    {'Cfg':<4}{'FE-ST ERLE(buck)':>16}{'echo-active':>14}{'converged':>10}")
    for c in CFGS:
        emit(f"    {c:<4}{fnum(gv(dev,c,'erle_fest_mean')):>16}"
             f"{fnum(gv(dev,c,'erle_active')):>14}"
             f"{fnum(gv(dev,c,'erle_conv')):>10}")
    emit("  Note: FE-ST ERLE (primary) = near-mic / output energy ratio over the [detected far single-talk] segment,")
    emit("        excluding double-talk -- the primary echo-cancellation figure. Low DT ERLE is by-design near-speech")
    emit("        protection, not a defect. The device 'echo-active/converged ERLE' cannot exclude double-talk (the")
    emit("        chip has no scene labels), so it is cross-check only; 'FE-ST ERLE(buck)' averages the leading")
    emit("        convergence buckets, comparable if the material starts with pure echo.")
    emit("")

    # ---- IV. Near-end fidelity ----
    emit("IV. Near-end fidelity (after cross-correlation alignment)")
    if aud:
        emit(f"  {'Cfg':<4}{'path delay(smp/ms)':>18}{'NE-ST corr':>12}{'DT corr':>12}")
        for c in CFGS:
            if c not in aud:
                continue
            dlabel = "{}/{:.0f}ms".format(aud[c]['delay_samp'], aud[c]['delay_ms'])
            emit(f"  {c:<4}{dlabel:>18}"
                 f"{fnum(aud[c]['nst_corr'],'{:.3f}'):>12}{fnum(aud[c]['dt_corr'],'{:.3f}'):>12}")
        cfgs_have = [c for c in CFGS if c in aud]
        if cfgs_have:
            floor = min(aud[c]['delay_ms'] for c in cfgs_have)
            emit(f"  Path-delay floor (shared linear front-end): {floor:.0f} ms; extra delay per back-end:")
            emit("    " + "  ".join(f"{c} +{aud[c]['delay_ms']-floor:.0f}ms" for c in cfgs_have))
        emit("  Note: NE-ST corr = transparency (higher is better); DT corr drops vs the mic because echo is removed,")
        emit("        so it is an ambiguous metric -- judge double-talk near-end fidelity by AECMOS DT-Other instead.")
    else:
        emit("  (needs numpy/librosa + wav files)")
    emit("")

    # ---- V. AECMOS (ground-truth segments) ----
    emit("V. AECMOS perceptual quality (Echo/Other, 1~5 higher is better; scene labels = ground truth)")
    if mos:
        emit(f"  {'Cfg':<4}{'FE-ST Echo':>12}{'NE-ST Other':>12}{'DT Echo':>10}"
             f"{'DT Other':>10}{'composite':>12}")
        for c in CFGS:
            m = mos.get(c)
            if not m:
                continue
            emit(f"  {c:<4}{fnum(m['fest_echo'],'{:.2f}'):>12}{fnum(m['nest_other'],'{:.2f}'):>12}"
                 f"{fnum(m['dt_echo'],'{:.2f}'):>10}{fnum(m['dt_other'],'{:.2f}'):>10}"
                 f"{fnum(m['comp'],'{:.2f}'):>12}")
        _kn = next((m['comp_n'] for m in mos.values() if m), 4)
        if _kn >= 4:
            emit("  composite = (FE-ST Echo + NE-ST Other + DT Echo + DT Other)/4  (Microsoft AEC Challenge convention)")
        else:
            emit(f"  composite = mean of the {_kn}/4 scenario scores present in this clip (missing scenarios excluded); with all 4 it matches the Microsoft AEC Challenge convention.")
    else:
        emit("  (needs numpy/librosa/onnxruntime + Run_*Stage_0.onnx + wav files)")
    emit("")

    # ---- VI. Paired comparison ----
    emit("VI. Paired comparison")
    for a, b, tag in PAIRS:
        emit(f"  -- {a} vs {b} ({tag}) --")

        def row(name, va, vb, better, unit="", fmt="{:.1f}"):
            sa = fnum(va, fmt); sb = fnum(vb, fmt)
            def _ok(x):
                return x is not None and not (isinstance(x, float) and math.isnan(x))
            if not (_ok(va) and _ok(vb)):
                verdict = "—"                 # a value is missing: not comparable (not a tie)
            elif abs(va - vb) <= 1e-9:
                verdict = "~tie"              # both present and equal: genuine tie
            else:
                lo = (va < vb)
                verdict = "win:" + (a if (lo == (better == "low")) else b)
            emit(f"    {name:<20}{sa+unit:>12}{sb+unit:>12}   {verdict}")

        row("CPU avg",        gv(dev,a,'cpu_avg'),      gv(dev,b,'cpu_avg'), "low", "%")
        row("CPU p95",        gv(dev,a,'cpu_p95'),      gv(dev,b,'cpu_p95'), "low", "%")
        row("CPU max",        gv(dev,a,'cpu_max'),      gv(dev,b,'cpu_max'), "low", "%")
        row("RTF",            gv(dev,a,'rtf'),          gv(dev,b,'rtf'), "high", "x", "{:.2f}")
        row("internal SRAM",  gv(dev,a,'sram_kb'),      gv(dev,b,'sram_kb'), "low", "KB")
        row("PSRAM",          gv(dev,a,'psram_kb'),     gv(dev,b,'psram_kb'), "low", "KB")
        row("RAM total",      gv(dev,a,'ram_total_kb'), gv(dev,b,'ram_total_kb'), "low", "KB", "{:.0f}")
        row("total(+flash)",  gv(dev,a,'footprint_total_kb'), gv(dev,b,'footprint_total_kb'), "low", "KB", "{:.0f}")
        # echo: primary = offline scene-aware ERLE (excludes double-talk); fall back to device bucket mean if no audio.
        if aud and a in aud and b in aud and gv(aud, a, 'erle_fe') is not None:
            row("FE-ST ERLE(offl)", gv(aud,a,'erle_fe'), gv(aud,b,'erle_fe'), "high", "dB")
            row("DT ERLE(offl)",    gv(aud,a,'erle_dt'), gv(aud,b,'erle_dt'), "high", "dB")
        else:
            row("FE-ST ERLE(dev)",  gv(dev,a,'erle_fest_mean'), gv(dev,b,'erle_fest_mean'), "high", "dB")
        if mos and a in mos and b in mos:
            row("AECMOS FE-ST Echo",  mos[a]['fest_echo'], mos[b]['fest_echo'], "high", "", "{:.2f}")
            row("AECMOS NE-ST Other", mos[a]['nest_other'], mos[b]['nest_other'], "high", "", "{:.2f}")
            row("AECMOS DT Echo",     mos[a]['dt_echo'], mos[b]['dt_echo'], "high", "", "{:.2f}")
            row("AECMOS DT Other",    mos[a]['dt_other'], mos[b]['dt_other'], "high", "", "{:.2f}")
            row("AECMOS composite",   mos[a]['comp'], mos[b]['comp'], "high", "", "{:.2f}")
        if aud and a in aud and b in aud:
            row("path delay",   aud[a]['delay_ms'], aud[b]['delay_ms'], "low", "ms", "{:.0f}")
            row("NE-ST corr",   aud[a]['nst_corr'], aud[b]['nst_corr'], "high", "", "{:.3f}")
        # compute-saving line
        ca, cb = gv(dev, a, 'cpu_avg'), gv(dev, b, 'cpu_avg')
        if ca and cb:
            emit(f"    -> {a} saves {(1-ca/cb)*100:.0f}% compute vs {b} (CPU avg {ca:.1f}% vs {cb:.1f}%)")
        emit("")

    with open("aec_report_en.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(OUT_LINES) + "\n")
    print("[written] " + os.path.join(OUT_DIR, "aec_report_en.txt"))


if __name__ == "__main__":
    main()
