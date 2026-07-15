# -*- coding: utf-8 -*-
"""Generate annotated waveform figures for test case 1.
Usage: python make_figs.py [zh|en]   (default: zh)"""
import numpy as np, wave
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
from matplotlib import font_manager

# Chinese font
for f in font_manager.fontManager.ttflist:
    pass
plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "Noto Sans CJK JP", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False


import sys
LANG = sys.argv[1] if len(sys.argv) > 1 else "zh"
SUF = "" if LANG == "zh" else "_en"
TXT = {
 "zh": {
  "scenes": ["回声段（远端单讲）", "近端单讲", "双讲"],
  "near": "near.wav（麦克风信号）", "far": "far.wav（远端参考）",
  "cfgs": ["A1 = SeekAudio AEC + WebRTC NS", "B1 = esp-sr FD-AEC + ns_pro（基线）",
           "A2 = SeekAudio AEC + AI 降噪", "B2 = esp-sr FD-AEC + NSNet2（基线）"],
  "cfgs_s": ["A1", "B1（基线）", "A2", "B2（基线）"],
  "ann1": "试听：偶发微弱残余回声（4–7s）", "ann2": "试听：微弱残余回声（34–35.5s）",
  "ann3": "可闻残余区间（4–7s）", "time": "时间（秒）",
  "t1": "图 1　测试素材波形与场景划分",
  "t2": "图 2　四配置处理输出波形（时间轴与图 1 对齐，红色标注为主观试听发现）",
  "t3": "图 3　回声段（0–10 秒）纵轴放大对比（±0.06 满幅，理想输出为静音）",
 },
 "en": {
  "scenes": ["Echo (FE single-talk)", "Near-end single-talk", "Double-talk"],
  "near": "near.wav (microphone)", "far": "far.wav (far-end reference)",
  "cfgs": ["A1 = SeekAudio AEC + WebRTC NS", "B1 = esp-sr FD-AEC + ns_pro (baseline)",
           "A2 = SeekAudio AEC + AI denoiser", "B2 = esp-sr FD-AEC + NSNet2 (baseline)"],
  "cfgs_s": ["A1", "B1 (baseline)", "A2", "B2 (baseline)"],
  "ann1": "Audible faint residual (4-7s)", "ann2": "Audible faint residual (34-35.5s)",
  "ann3": "Audible residual interval (4-7s)", "time": "Time (s)",
  "t1": "Fig. 1  Test material waveforms and scene partitioning",
  "t2": "Fig. 2  Processed outputs of the four configurations (red = audible residuals found by listening)",
  "t3": "Fig. 3  Echo segment (0-10 s), vertical axis magnified (\u00b10.06 FS; ideal output is silence)",
 },
}[LANG]

FS = 16000
def load(p):
    w = wave.open(p)
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return x

near, far = load("near.wav"), load("far.wav")
a1, b1, a2, b2 = load("a1.wav"), load("b1.wav"), load("a2.wav"), load("b2.wav")
T = len(near) / FS

# decimated min-max envelope for fast, faithful waveform rendering
def envelope(x, npts=4000):
    n = len(x); step = max(1, n // npts)
    m = (n // step) * step
    seg = x[:m].reshape(-1, step)
    t = np.arange(seg.shape[0]) * step / FS
    return t, seg.min(1), seg.max(1)

SCENES = [(0, 10, TXT["scenes"][0], "#fde4d4"),
          (10, 26, TXT["scenes"][1], "#ddefdc"),
          (26, 36, TXT["scenes"][2], "#e6dff2")]
WAVE = "#2b4a8b"

def draw_track(ax, x, label, ylim=1.0, bands=True, band_labels=False):
    t, lo, hi = envelope(x)
    if bands:
        for s, e, name, c in SCENES:
            ax.axvspan(s, min(e, T), color=c, zorder=0)
            if band_labels:
                ax.text((s + min(e, T)) / 2, ylim * 0.82, name, ha="center", va="center",
                        fontsize=10.5, color="#444444", zorder=3)
    ax.fill_between(t, lo, hi, color=WAVE, lw=0.3, zorder=2)
    ax.set_ylim(-ylim, ylim); ax.set_xlim(0, T)
    ax.text(0.006, 0.94, label, transform=ax.transAxes, fontsize=11.5, fontweight="bold",
            va="top", ha="left", color="#111111",
            bbox=dict(facecolor="white", edgecolor="#999999", boxstyle="round,pad=0.25", alpha=0.9), zorder=4)
    ax.grid(axis="x", color="#bbbbbb", lw=0.4, alpha=0.5)
    ax.set_yticks([-ylim, 0, ylim])
    ax.tick_params(labelsize=9)

# ---------- Figure 1: near + far ----------
fig, axes = plt.subplots(2, 1, figsize=(11, 3.8), sharex=True)
draw_track(axes[0], near, TXT["near"], band_labels=True)
draw_track(axes[1], far, TXT["far"])
axes[1].set_xlabel(TXT["time"], fontsize=10.5)
axes[1].set_xticks(np.arange(0, 37, 2))
fig.suptitle(TXT["t1"], fontsize=13, fontweight="bold", y=0.99)
fig.tight_layout(rect=[0, 0, 1, 0.96])
fig.savefig("fig1_material%s.png" % SUF, dpi=170)
plt.close(fig)

# ---------- Figure 2: four outputs ----------
fig, axes = plt.subplots(4, 1, figsize=(11, 7.0), sharex=True)
for ax, x, lb in zip(axes, [a1, b1, a2, b2],
                     TXT["cfgs"]):
    draw_track(ax, x, lb, band_labels=(ax is axes[0]))
axes[-1].set_xlabel(TXT["time"], fontsize=10.5)
axes[-1].set_xticks(np.arange(0, 37, 2))
# subjective annotations on B1
axB1 = axes[1]
for (s, e, txt, ty) in [(4, 7, TXT["ann1"], 0.62),
                        (34, 35.5, TXT["ann2"], 0.62)]:
    axB1.plot([s, e], [-0.52, -0.52], color="#c0392b", lw=2.2, solid_capstyle="butt", zorder=5)
    axB1.plot([s, s], [-0.6, -0.44], color="#c0392b", lw=1.4, zorder=5)
    axB1.plot([e, e], [-0.6, -0.44], color="#c0392b", lw=1.4, zorder=5)
    axB1.text((s + e) / 2 if e < 30 else e - 4.4, -0.85, txt, ha="center", fontsize=9.5,
              color="#c0392b", zorder=5)
fig.suptitle(TXT["t2"], fontsize=13, fontweight="bold", y=0.995)
fig.tight_layout(rect=[0, 0, 1, 0.97])
fig.savefig("fig2_outputs%s.png" % SUF, dpi=170)
plt.close(fig)

# ---------- Figure 3: echo-segment zoom, amplified ----------
ZL = 0.06
fig, axes = plt.subplots(4, 1, figsize=(11, 6.4), sharex=True)
for ax, x, lb in zip(axes, [a1, b1, a2, b2], TXT["cfgs_s"]):
    n0, n1 = 0, int(10 * FS)
    seg = x[n0:n1]
    t, lo, hi = envelope(seg, npts=3000)
    ax.axvspan(0, 10, color="#fde4d4", zorder=0)
    ax.fill_between(t, lo, hi, color=WAVE, lw=0.3, zorder=2)
    ax.set_xlim(0, 10); ax.set_ylim(-ZL, ZL)
    ax.set_yticks([-ZL, 0, ZL])
    ax.text(0.008, 0.92, lb, transform=ax.transAxes, fontsize=11.5, fontweight="bold", va="top",
            bbox=dict(facecolor="white", edgecolor="#999999", boxstyle="round,pad=0.25", alpha=0.9), zorder=4)
    ax.grid(axis="x", color="#bbbbbb", lw=0.4, alpha=0.5)
    ax.tick_params(labelsize=9)
axes[1].plot([4, 7], [-0.045, -0.045], color="#c0392b", lw=2.2, zorder=5)
axes[1].text(5.5, -0.055, TXT["ann3"], ha="center", fontsize=9.5, color="#c0392b", zorder=5)
axes[-1].set_xlabel(TXT["time"], fontsize=10.5)
fig.suptitle(TXT["t3"], fontsize=13, fontweight="bold", y=0.995)
fig.tight_layout(rect=[0, 0, 1, 0.97])
fig.savefig("fig3_echo_zoom%s.png" % SUF, dpi=170)
plt.close(fig)
print("figures done")
