[简体中文](README.md) | English

# seekaudio_aec_test

![Compute saved](https://img.shields.io/badge/compute_saved-~54%25-brightgreen) ![RTF](https://img.shields.io/badge/RTF-3.56×-brightgreen) ![FE-ST ERLE](https://img.shields.io/badge/FE--ST_ERLE-21.5dB-blue) ![AECMOS](https://img.shields.io/badge/AECMOS-3.85-blue) ![Platform](https://img.shields.io/badge/platform-ESP32--S3-lightgrey)

> ### ⚡ Half the compute, cleaner echo cancellation
>
> On the ESP32-S3, **SeekAudio AEC uses about half the compute of the official esp-sr baseline (A1 saves ~54%, A2 saves ~48%), while cancelling echo more effectively (far-end single-talk ERLE 8–12 dB higher) and scoring better on perceptual quality (AECMOS).**
>
> - 🚀 **Half the compute** — CPU load **28%** vs baseline **60%**, RTF **3.56×** vs **1.65×**
> - 🎯 **Stronger echo cancellation** — FE-ST ERLE **21.5 dB** vs **9.7 dB**, residual echo **12 dB** lower
> - 👂 **Better perceived quality** — AECMOS composite **3.85** vs **3.48**, echo-suppression score **4.04** vs **3.10**

A complete, reproducible A/B benchmark of **SeekAudio AEC** versus **esp-sr AFE AEC** on the ESP32-S3: same board, same test material, same automated report tool. Four configurations run back-to-back and every number can be reproduced with one flash-and-run cycle.

## Results at a glance

Multi-sample averages (ESP32-S3 @240 MHz, 16 kHz, 32 ms frames, Microsoft AEC Challenge dataset):

> **A1** = SeekAudio AEC + WebRTC NS  **A2** = SeekAudio AEC + AI noise reduction
> **B1** = esp-sr FD-AEC + ns_pro (baseline; ns_pro is esp-sr's built-in WebRTC NS)  **B2** = esp-sr FD-AEC + NSNet2 (baseline)
> A1/B1 share the WebRTC NS tier and A2/B2 share the AI tier — a like-for-like pairing.

| Metric | A1 | A2 | B1 (baseline) | B2 (baseline) |
|---|---|---|---|---|
| CPU load, avg | **28.1%** | **37.8%** | 60.5% | 73.2% |
| Real-time factor (higher is better) | 3.56× | 2.64× | 1.65× | 1.37× |
| Compute saved vs baseline | **~54%** | **~48%** | — | — |
| FE single-talk ERLE (dB, higher is better) | **21.5** | **29.4** | 9.7 | 17.8 |
| Residual echo (dBFS, lower is better) | **−46.6** | **−54.5** | −34.8 | −42.9 |
| AECMOS FE-ST Echo | **4.04** | **4.04** | 3.10 | 3.62 |
| AECMOS NE-ST Other | 3.46 | 3.21 | 3.68 | 3.77 |
| AECMOS DT Echo | **4.19** | 4.25 | 3.86 | 4.26 |
| AECMOS DT Other | 4.09 | 3.74 | 4.09 | 4.16 |
| AECMOS composite (1–5, higher is better) | **3.85** | 3.80 | 3.48 | 3.77 |
| Internal SRAM (KB) | 75.0 | 192.5 | 12.4 | 21.1 |
| PSRAM (KB) | 192.7 | 192.7 | 182.9 | 520.2 |
| Flash model partition (KB) | — | — | — | 1024 |

Metric definitions, per-row analysis and the AECMOS sub-score trade-off discussion are in the solution article (identical table).

## 📚 Documentation

| Document | 中文 | English |
|---|---|---|
| 📄 Solution article (architecture / measurements / analysis) | [中文](docs/article/README.md) | [EN](docs/article/README_EN.md) |
| 🧪 Test cases ×10 (subjective + objective) | 见下方索引 | see [case index](#-test-case-index) below |
| 📊 Full evaluation report v1.0 | [中文](evaluationReport/SeekAudio_AEC_评测报告_v1.0_2026-07.txt) | [EN](evaluationReport/SeekAudio_AEC_Evaluation_Report_v1.0_2026-07.txt) |
| 🛠 Report tool user guide | [中文](tools/aec_report_使用说明.txt) | [EN](tools/aec_report_user_guide_EN.txt) |

## The four configurations

| Config | Pipeline | Role |
|---|---|---|
| A1 | SeekAudio AEC + WebRTC NS | Device under test, classic NS tier |
| A2 | SeekAudio AEC + AI noise reduction | Device under test, AI NS tier |
| B1 | esp-sr FD-AEC + ns_pro | Baseline, classic NS tier (ns_pro is esp-sr's built-in WebRTC NS) |
| B2 | esp-sr FD-AEC + NSNet2 | Baseline, AI NS tier |

All four share the same input (near.wav / far.wav) and run sequentially in a single boot, each writing one output WAV. Baseline components are pinned to exact versions: `esp-sr==2.4.5`, `esp-dsp==1.8.0` (see `main/idf_component.yml`); the B group keeps esp-sr's default memory placement.

## 🧪 Test case index

Ten cases covering full-scenario clips, long double-talk, echo-only, time-varying paths with movement, and dense alternating double-talk. Each includes annotated waveform figures, downloadable raw audio and the full automated report:

| # | Case highlight | 中文 | English |
|---|---|---|---|
| 1 | Full-scenario comparison: echo / near-end / double-talk | [中文](docs/cases/case1/README.md) | [EN](docs/cases/case1/README_EN.md) |
| 2 | Long double-talk clip: convergence speed and DT residual | [中文](docs/cases/case2/README.md) | [EN](docs/cases/case2/README_EN.md) |
| 3 | Double-talk with movement: baseline amplifies the echo (negative ERLE) | [中文](docs/cases/case3/README.md) | [EN](docs/cases/case3/README_EN.md) |
| 4 | Double-talk clip: opening-segment convergence | [中文](docs/cases/case4/README.md) | [EN](docs/cases/case4/README_EN.md) |
| 5 | Echo-only hard clip: residual magnitude comparison | [中文](docs/cases/case5/README.md) | [EN](docs/cases/case5/README_EN.md) |
| 6 | Long echo-only clip: point-by-point residual comparison | [中文](docs/cases/case6/README.md) | [EN](docs/cases/case6/README_EN.md) |
| 7 | Movement + very low echo level: another baseline echo-amplification case | [中文](docs/cases/case7/README.md) | [EN](docs/cases/case7/README_EN.md) |
| 8 | Two echo segments: an audible gap in the opening span | [中文](docs/cases/case8/README.md) | [EN](docs/cases/case8/README_EN.md) |
| 9 | Dense alternating double-talk: one of the widest gaps in the suite | [中文](docs/cases/case9/README.md) | [EN](docs/cases/case9/README_EN.md) |
| 10 | Dense double-talk: the case where the baseline's FE perception score collapses | [中文](docs/cases/case10/README.md) | [EN](docs/cases/case10/README_EN.md) |

## 🚀 Quick start

**Hardware**: verified on the **ESP32-S3-BOX-3**; any ESP32-S3 module with **16 MB flash** (the partition table totals ~14.1 MB; 8 MB modules cannot be flashed — see `partitions.csv`) and PSRAM should work.

**Software**: ESP-IDF 5.3 – 5.5 (verified); on the PC, Python 3 with `pip install numpy librosa onnxruntime littlefs-python`.

```bash
# 1. Build
idf.py fullclean
idf.py set-target esp32s3
idf.py build

# 2. Pack the test material into a littlefs image
#    (2304 x 4096 = 0x900000, exactly the storage partition size)
python -m littlefs create --block-size 4096 --block-count 2304 fs_files/ fs.img

# 3. Flash bootloader / partition table / app / material image / esp-sr models in one go
#    (-p: your serial port — COMx on Windows, /dev/ttyUSBx on Linux)
esptool.py -p COM3 -b 921600 write_flash 0x0 build/bootloader/bootloader.bin 0x8000 build/partition_table/partition-table.bin 0x10000 build/seekaudio_aec_test.bin 0x410000 fs.img 0xD10000 build/srmodels/srmodels.bin

# 4. Run and watch (the four configs execute sequentially, writing WAVs to littlefs;
#    save the serial log as log.txt afterwards)
idf.py -p COM3 monitor

# 5. Read back and unpack the results to obtain a1/a2/b1/b2.wav
esptool.py -p COM3 read_flash 0x410000 0x900000 fs_out.img
python -m littlefs extract --block-size 4096 fs_out.img results/

# 6. Assemble the report inputs and generate the report:
#    results/ should already contain the unpacked near/far/a1/a2/b1/b2.wav; add two things --
#    (a) log.txt saved from step 4 (all device-side data -- compute, memory, delay --
#        comes from it; without it the report only has offline audio metrics)
#    (b) the AECMOS scoring model (omitted section if missing)
cp tools/Run_1663915512_Stage_0.onnx results/
cd results
python ../tools/aec_report_en.py --echo 0:10 --near 10:26 --dt 26:36
```

Common switches (see `main/bench_config.h`; all overridable via `idf.py -D<MACRO>=0/1`): `RUN_A1/RUN_A2/RUN_B1/RUN_B2` enable/disable individual configs. **B2 requires the esp-sr model partition (srmodels) to be flashed — use `-DRUN_B2=0` otherwise.**

## 📁 Repository layout

```
components/seekaudio_aec/   SeekAudio AEC library (proprietary binary + public header)
main/                       Benchmark app (config scheduling, timing, littlefs I/O)
fs_files/                   Test material (near.wav mic signal / far.wav far-end reference)
output_dir/case1..case10/   Raw outputs of the 10 test cases (material / 4 outputs / log / bilingual reports)
evaluationReport/           Full evaluation report (CN / EN)
tools/                      aec_report report tool (CN / EN) + AECMOS model
docs/                       Solution article and test cases (CN / EN)
partitions.csv              Partition table (storage=littlefs material & outputs, model=esp-sr models)
```

## ⚖️ Fairness notes

- **Group B keeps esp-sr's official default memory placement** (main buffers in PSRAM); nothing was changed to the baseline's disadvantage. Comparison components are pinned: `esp-sr==2.4.5`, `esp-dsp==1.8.0`.
- The macro **`B_AEC_INTERNAL_SRAM`** (`main/fd_aec_backend.cpp`, default 0) is kept in the code: enabling it moves B1/B2's key buffers into internal SRAM, reducing their measured CPU load by roughly 15% / 10% — but internal SRAM usage soars to about 130 KB / 200 KB+, and the compute cost still remains far above the SeekAudio configs. Trading scarce internal SRAM for a modest compute gain is a losing configuration, hence off by default. You are welcome to re-test with `idf.py -DB_AEC_INTERNAL_SRAM=1 build`; the conclusions do not flip.
- **Library baseline**: all reports and documented numbers in this repository were measured with the `libseekaudio_aec.a` from commit [`ca75b3d`](https://github.com/seekaudio/seekaudio_aec_test/commit/ca75b3dae9f4d831fc60ac6ada16774ce2ec3429) (use `git checkout ca75b3d` to align exactly). Library optimizations made after that commit are not reflected in existing reports unless a report explicitly states a re-test.

## License

The benchmark code and documentation in this repository are released under the MIT license; `libseekaudio_aec.a` under `components/seekaudio_aec/lib/` is a proprietary SeekAudio binary licensed for evaluation use only. See [LICENSE](LICENSE) and [components/seekaudio_aec/LICENSE.txt](components/seekaudio_aec/LICENSE.txt).

## Contact

For commercial licensing: [https://www.seekaudio.cn/](https://www.seekaudio.cn/)
