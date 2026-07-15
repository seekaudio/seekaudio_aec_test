# -*- coding: utf-8 -*-
"""Generate figures + bilingual case docs + output_dir readmes for cases 1-10."""
import os, re, sys, json, wave
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from case_config import CASES

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "Noto Sans CJK JP", "Noto Sans CJK HK", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False
FS = 16000
BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(BASE, "..", "..", "output_dir"))  # repo layout
DOCS = BASE
OUT = os.path.join(BASE, "_out_readmes")
WAVE = "#2b4a8b"
COLORS = dict(echo="#fde4d4", near="#ddefdc", dt="#e6dff2")
SCN = dict(zh=dict(echo="回声段", near="近端单讲", dt="双讲"),
           en=dict(echo="Echo", near="Near-end single-talk", dt="Double-talk"))
TT = dict(zh=dict(t1="图 1　测试素材波形与场景划分",
                  t2="图 2　四配置处理输出波形（红色标注为主观试听发现）",
                  t3="图 3　关键区间纵轴放大对比（理想输出为静音）",
                  near="near.wav（麦克风信号）", far="far.wav（远端参考）", time="时间（秒）",
                  cfgs=["A1 = SeekAudio AEC + WebRTC NS","B1 = esp-sr FD-AEC + ns_pro（基线）",
                        "A2 = SeekAudio AEC + AI 降噪","B2 = esp-sr FD-AEC + NSNet2（基线）"],
                  cfgs_s=["A1","B1（基线）","A2","B2（基线）"]),
          en=dict(t1="Fig. 1  Test material waveforms and scene partitioning",
                  t2="Fig. 2  Processed outputs of the four configurations (red = audible residuals found by listening)",
                  t3="Fig. 3  Key-interval comparison, vertical axis magnified (ideal output is silence)",
                  near="near.wav (microphone)", far="far.wav (far-end reference)", time="Time (s)",
                  cfgs=["A1 = SeekAudio AEC + WebRTC NS","B1 = esp-sr FD-AEC + ns_pro (baseline)",
                        "A2 = SeekAudio AEC + AI denoiser","B2 = esp-sr FD-AEC + NSNet2 (baseline)"],
                  cfgs_s=["A1","B1 (baseline)","A2","B2 (baseline)"]))

def load(p):
    w = wave.open(p)
    return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)/32768.0

def envelope(x, t0=0.0, npts=4000):
    n = len(x); step = max(1, n//npts); m = (n//step)*step
    seg = x[:m].reshape(-1, step)
    return t0 + np.arange(seg.shape[0])*step/FS, seg.min(1), seg.max(1)

def bands(ax, scenes, T, ylim, labels=False):
    for typ, segs in scenes.items():
        for (s, e) in segs:
            ax.axvspan(s, min(e, T), color=COLORS[typ], zorder=0)

def legend(fig, scenes, lang):
    pats = [Patch(facecolor=COLORS[t], label=SCN[lang][t]) for t in ("echo","near","dt") if scenes.get(t)]
    fig.legend(handles=pats, loc="upper right", ncol=3, fontsize=9.5, frameon=False,
               bbox_to_anchor=(0.995, 1.0))

def track(ax, x, label, scenes, T, ylim=1.0):
    bands(ax, scenes, T, ylim)
    t, lo, hi = envelope(x)
    ax.fill_between(t, lo, hi, color=WAVE, lw=0.3, zorder=2)
    ax.set_xlim(0, T); ax.set_ylim(-ylim, ylim); ax.set_yticks([-ylim, 0, ylim])
    ax.text(0.006, 0.93, label, transform=ax.transAxes, fontsize=10.5, fontweight="bold", va="top",
            bbox=dict(facecolor="white", edgecolor="#999999", boxstyle="round,pad=0.22", alpha=0.9), zorder=4)
    ax.grid(axis="x", color="#bbbbbb", lw=0.4, alpha=0.5); ax.tick_params(labelsize=8.5)

def annotate(ax, s, e, txt, ylim):
    y = -ylim*0.55
    ax.plot([s, e], [y, y], color="#c0392b", lw=2.0, solid_capstyle="butt", zorder=5)
    for xx in (s, e): ax.plot([xx, xx], [y-ylim*0.07, y+ylim*0.07], color="#c0392b", lw=1.3, zorder=5)
    cx = (s+e)/2
    ax.text(cx, -ylim*0.85, txt, ha="center", fontsize=8.8, color="#c0392b", zorder=5, clip_on=False)

def gen_figs(ci, cfg, lang):
    d = os.path.join(SRC, f"case{ci}")
    near, far = load(f"{d}/near.wav"), load(f"{d}/far.wav")
    outs = {k: load(f"{d}/{k}.wav") for k in ("a1","b1","a2","b2")}
    T = cfg["dur"]; L = TT[lang]; suf = "" if lang == "zh" else "_en"
    od = os.path.join(DOCS, f"case{ci}"); os.makedirs(od, exist_ok=True)
    # fig1
    fig, axes = plt.subplots(2, 1, figsize=(11, 3.8), sharex=True)
    track(axes[0], near, L["near"], cfg["scenes"], T)
    track(axes[1], far, L["far"], cfg["scenes"], T)
    axes[1].set_xlabel(L["time"], fontsize=10)
    legend(fig, cfg["scenes"], lang)
    fig.suptitle(L["t1"], fontsize=12.5, fontweight="bold", x=0.02, ha="left", y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.94]); fig.savefig(f"{od}/fig1_material{suf}.png", dpi=160); plt.close(fig)
    # fig2
    fig, axes = plt.subplots(4, 1, figsize=(11, 7.0), sharex=True)
    axmap = {}
    for ax, key, lb in zip(axes, ["a1","b1","a2","b2"], L["cfgs"]):
        track(ax, outs[key], lb, cfg["scenes"], T); axmap[key] = ax
    for (trk, s, e, zh, en) in cfg["ann"]:
        annotate(axmap[trk], s, e, zh if lang == "zh" else en, 1.0)
    axes[-1].set_xlabel(L["time"], fontsize=10)
    legend(fig, cfg["scenes"], lang)
    fig.suptitle(L["t2"], fontsize=12.5, fontweight="bold", x=0.02, ha="left", y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.965]); fig.savefig(f"{od}/fig2_outputs{suf}.png", dpi=160); plt.close(fig)
    # fig3 zoom, adaptive ylim
    z0, z1 = cfg["zoom"]; n0, n1 = int(z0*FS), int(z1*FS)
    peak = max(np.percentile(np.abs(outs[k][n0:n1]), 99.5) for k in outs)
    ylim = float(min(1.0, max(0.02, round(peak*1.35, 2))))
    fig, axes = plt.subplots(4, 1, figsize=(11, 6.4), sharex=True)
    axmap = {}
    for ax, key, lb in zip(axes, ["a1","b1","a2","b2"], L["cfgs_s"]):
        seg = outs[key][n0:n1]
        bands(ax, cfg["scenes"], T, ylim)
        t, lo, hi = envelope(seg, t0=z0, npts=3000)
        ax.fill_between(t, lo, hi, color=WAVE, lw=0.3, zorder=2)
        ax.set_xlim(z0, z1); ax.set_ylim(-ylim, ylim); ax.set_yticks([-ylim, 0, ylim])
        ax.text(0.008, 0.92, lb, transform=ax.transAxes, fontsize=10.5, fontweight="bold", va="top",
                bbox=dict(facecolor="white", edgecolor="#999999", boxstyle="round,pad=0.22", alpha=0.9), zorder=4)
        ax.grid(axis="x", color="#bbbbbb", lw=0.4, alpha=0.5); ax.tick_params(labelsize=8.5)
        axmap[key] = ax
    for (trk, s, e, zh, en) in cfg["ann"]:
        if e > z0 and s < z1:
            annotate(axmap[trk], max(s, z0), min(e, z1), zh if lang == "zh" else en, ylim)
    axes[-1].set_xlabel(L["time"], fontsize=10)
    t3 = TT[lang]["t3"].replace("（理想输出为静音）", f"（{z0}–{z1} 秒，±{ylim} 满幅；理想输出为静音）") if lang == "zh" \
         else TT[lang]["t3"].replace("(ideal output is silence)", f"({z0}-{z1} s, ±{ylim} FS; ideal output is silence)")
    fig.suptitle(t3, fontsize=12.5, fontweight="bold", x=0.02, ha="left", y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.965]); fig.savefig(f"{od}/fig3_zoom{suf}.png", dpi=160); plt.close(fig)

# ---------------- markdown ----------------
M = json.load(open(os.path.join(BASE, "metrics.json")))
K = ["A1","A2","B1","B2"]
def row(name, key, fmt, better, m):
    vals = [m[k].get(key) for k in K]
    if all(v is None for v in vals): return None
    def cell(i, k):
        v = m[k].get(key)
        if v is None: return "—"
        s = fmt % v
        pair = {"A1":"B1","B1":"A1","A2":"B2","B2":"A2"}.get(k)
        if pair:
            o = m[pair].get(key)
            if o is not None and ((better=="hi" and v > o) or (better=="lo" and v < o)):
                return f"**{s}**"
        return s
    return "| " + name + " | " + " | ".join(cell(i, k) for i, k in enumerate(K)) + " |"

def tables(m, lang):
    zh = lang == "zh"
    hdr = "| " + ("指标" if zh else "Metric") + " | A1 | A2 | B1" + ("（基线）" if zh else " (baseline)") + " | B2" + ("（基线）" if zh else " (baseline)") + " |\n|---|---|---|---|---|\n"
    t1 = [row("CPU 平均负载（%）" if zh else "CPU load, avg (%)", "cpu", "%.1f", "lo", m),
          row("实时率 RTF（越高越好）" if zh else "Real-time factor (higher is better)", "rtf", "%.2f×", "hi", m)]
    rows2 = [row("FE-ST ERLE（dB，越高越好）" if zh else "FE-ST ERLE (dB, higher is better)", "erle", "%.1f", "hi", m),
             row("残余回声（dBFS，越低越好）" if zh else "Residual echo (dBFS, lower is better)", "resid", "%.1f", "lo", m),
             row("NE-ST 近端相关度" if zh else "NE-ST correlation", "necorr", "%.3f", "hi", m),
             row("链路延迟（ms）" if zh else "Path delay (ms)", "delay", "%d", "lo", m),
             row("AECMOS FE-ST Echo", "mos_fe", "%.2f", "hi", m),
             row("AECMOS NE-ST Other", "mos_ne", "%.2f", "hi", m),
             row("AECMOS DT Echo", "mos_dte", "%.2f", "hi", m),
             row("AECMOS DT Other", "mos_dto", "%.2f", "hi", m),
             row("AECMOS 综合" if zh else "AECMOS composite", "mos", "%.2f", "hi", m)]
    t1 = hdr + "\n".join(r for r in t1 if r)
    t2 = hdr + "\n".join(r for r in rows2 if r)
    return t1, t2

def scene_lines(cfg, lang):
    zh = lang == "zh"; out = []
    names = SCN[lang]
    for typ in ("echo","near","dt"):
        segs = cfg["scenes"].get(typ)
        if not segs: continue
        span = "，".join(f"{s}–{e} 秒" for s, e in segs) if zh else ", ".join(f"{s}-{e} s" for s, e in segs)
        out.append(f"- **{names[typ]}**：{span}" if zh else f"- **{names[typ]}**: {span}")
    return "\n".join(out)

def case_md(ci, cfg, lang):
    m = M[f"case{ci}"]; zh = lang == "zh"; suf = "" if zh else "_en"
    L = lambda a, b: a if zh else b
    t1, t2 = tables(m, lang)
    OD = f"../../../output_dir/case{ci}"
    files_tbl = (f"| 文件 | 说明 |\n|---|---|\n"
                 f"| [near.wav]({OD}/near.wav) / [far.wav]({OD}/far.wav) | 测试素材（麦克风 / 远端参考） |\n"
                 f"| [a1.wav]({OD}/a1.wav) [b1.wav]({OD}/b1.wav) [a2.wav]({OD}/a2.wav) [b2.wav]({OD}/b2.wav) | 四配置在 ESP32-S3 上的处理输出 |\n"
                 f"| [log.txt]({OD}/log.txt) | 设备串口日志 |\n"
                 f"| [aec_report.txt]({OD}/aec_report.txt) / [aec_report_en.txt]({OD}/aec_report_en.txt) | 完整自动化报告（中 / 英） |") if zh else (
                 f"| File | Description |\n|---|---|\n"
                 f"| [near.wav]({OD}/near.wav) / [far.wav]({OD}/far.wav) | Test material (microphone / far-end reference) |\n"
                 f"| [a1.wav]({OD}/a1.wav) [b1.wav]({OD}/b1.wav) [a2.wav]({OD}/a2.wav) [b2.wav]({OD}/b2.wav) | The four configurations' outputs on the ESP32-S3 |\n"
                 f"| [log.txt]({OD}/log.txt) | Device serial log |\n"
                 f"| [aec_report.txt]({OD}/aec_report.txt) / [aec_report_en.txt]({OD}/aec_report_en.txt) | Full automated report (CN / EN) |")
    tool = "aec_report.py" if zh else "aec_report_en.py"
    subj = "\n".join("- " + s for s in cfg[f"subj_{lang}"])
    verdict = "\n\n".join(cfg[f"verdict_{lang}"])
    lang_line = "简体中文 | [English](README_EN.md)" if zh else "[简体中文](README.md) | English"
    art = "../../article/README.md" if zh else "../../article/README_EN.md"
    body = f"""{lang_line}

# {L('SeekAudio AEC 测试用例', 'SeekAudio AEC Test Case')} {ci}

**{cfg[f'title_{lang}']}** · {L('ESP32-S3 实测 · 主观 + 客观双重评估', 'measured on ESP32-S3 · subjective + objective evaluation')}

## {L('一、素材与场景', '1. Material and scenes')}

{cfg[f'prov_{lang}']} {L('人工试听标注场景边界如下：', 'Scene boundaries were annotated by listening:')}

{scene_lines(cfg, lang)}

{L('四个被测配置与', 'The four configurations match the ')}[{L('主文章', 'main article')}]({art}){L('一致（A1/B1 同为 WebRTC NS 降噪档、A2/B2 同为 AI 降噪档，两两对位公平）。四路输出均在 ESP32-S3（240 MHz，16 kHz，32 ms 帧）上实际运行产生。', ' (A1/B1 share the WebRTC NS tier, A2/B2 share the AI tier - a like-for-like pairing). All outputs were produced on an ESP32-S3 (240 MHz, 16 kHz, 32 ms frames).')}

**{L('本用例原始输出文件', 'Raw output files of this case')}**{L('（点击即可下载试听 / 查看）：', ' (click to download / listen / view):')}

{files_tbl}

## {L('二、主观评估：眼见为实，耳听为实', '2. Subjective evaluation: see it, hear it')}

![fig1](fig1_material{suf}.png)

![fig2](fig2_outputs{suf}.png)

![fig3](fig3_zoom{suf}.png)

**{L('试听结论（佩戴耳机逐段对听，欢迎下载上方 wav 亲自验证）：', 'Listening verdict (headphones, segment-by-segment A/B; download the WAVs above and verify yourself):')}**

{subj}

## {L('三、客观数据', '3. Objective data')}

{L('指标体系与主文章一致（微软 AEC Challenge 方法 + AECMOS + ERLE），由', 'Metrics follow the main article (Microsoft AEC Challenge methodology + AECMOS + ERLE), computed by')} [{tool}](../../../tools/{tool}) {L('自动生成；加粗表示同档对比（A1 对 B1、A2 对 B2）中的占优方。', 'automatically; bold marks the winner within each same-tier pair (A1 vs B1, A2 vs B2).')}

**{L('设备端计算性能', 'On-device compute')}**

{t1}

**{L('回声抑制与感知质量', 'Echo suppression and perceptual quality')}**

{t2}

## {L('四、分析与判定', '4. Analysis and verdict')}

{verdict}

**{L('复现本用例', 'Reproducing this case')}**{L('（按仓库主页 README 完成编译烧写运行，保存串口日志为 log.txt，解包 littlefs 后与 AECMOS 模型放入同一目录，执行）：', ' (build/flash/run per the repo README, save the serial log as log.txt, unpack littlefs, add the AECMOS model to the same folder, then run):')}

```bash
python {tool} {cfg['cmd']}
```

---

*{L('测试条件：ESP32-S3 @ 240 MHz，16 kHz，32 ms/帧；对比基线 esp-sr v2.4.5、esp-dsp v1.8.0；波形图由 make_figs_v2.py 生成；评测库基线为提交 `ca75b3d`，此后的库优化不体现于本报告。', 'Test conditions: ESP32-S3 @ 240 MHz, 16 kHz, 32 ms/frame; baselines esp-sr v2.4.5, esp-dsp v1.8.0; figures generated by make_figs_v2.py; library baseline is commit `ca75b3d` - later library optimizations are not reflected in this report.')}*
"""
    return body

def out_readme(ci, cfg):
    zh_scenes = scene_lines(cfg, "zh").replace("- **", "").replace("**", "")
    en_scenes = scene_lines(cfg, "en").replace("- **", "").replace("**", "")
    return f"""[测试用例 {ci} / Test case {ci}]

素材来源：{cfg["prov_zh"].replace("素材取自","取自")}
人工试听标注的场景边界：
{zh_scenes}

评测命令（将本目录 wav、log.txt 与 tools 下的 AECMOS 模型放入同一目录后执行）：
python aec_report.py {cfg['cmd']}
python aec_report_en.py {cfg['cmd']}

本用例的图文分析（主观 + 客观）见 docs/cases/case{ci}/（中英双语）。

--------------------------------------------------------------------

Material: {cfg['prov_en']}
Scene boundaries annotated by listening:
{en_scenes}

Report commands (put this folder's wav files, log.txt and the AECMOS model from tools/ in one directory, then run):
python aec_report.py {cfg['cmd']}
python aec_report_en.py {cfg['cmd']}

Full illustrated analysis (subjective + objective) of this case: docs/cases/case{ci}/ (CN / EN).
"""

for ci, cfg in CASES.items():
    for lang in ("zh", "en"):
        gen_figs(ci, cfg, lang)
        p = os.path.join(DOCS, f"case{ci}", "README.md" if lang == "zh" else "README_EN.md")
        open(p, "w", encoding="utf8").write(case_md(ci, cfg, lang))
    od = os.path.join(OUT, f"case{ci}"); os.makedirs(od, exist_ok=True)
    open(os.path.join(od, "readme.txt"), "w", encoding="utf8").write(out_readme(ci, cfg))
    print(f"case{ci} done")
print("ALL DONE")
