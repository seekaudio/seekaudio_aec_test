简体中文 | [English](README_EN.md)

# seekaudio_aec_test

![算力节省](https://img.shields.io/badge/算力节省-~54%25-brightgreen) ![RTF](https://img.shields.io/badge/RTF-3.56×-brightgreen) ![远端单讲ERLE](https://img.shields.io/badge/远端单讲ERLE-21.5dB-blue) ![AECMOS综合](https://img.shields.io/badge/AECMOS综合-3.85-blue) ![平台](https://img.shields.io/badge/平台-ESP32--S3-lightgrey)

> ### ⚡ 算力砍半，回声消得更干净
>
> 在 ESP32-S3 上，**SeekAudio AEC 相比 esp-sr 官方基线节省约一半算力（A1 省约 54%、A2 省约 48%），同时回声消除更强（远端单讲 ERLE 高 8–12 dB），感知质量（AECMOS）更优。**
>
> - 🚀 **算力省一半** —— CPU 平均负载 **28%** vs 基线 **60%**，RTF **3.56×** vs **1.65×**
> - 🎯 **回声消除更强** —— 远端单讲 ERLE **21.5 dB** vs **9.7 dB**，残余回声低 **12 dB**
> - 👂 **听感更优** —— AECMOS 综合 **3.85** vs **3.48**，回声抑制感知 **4.04** vs **3.10**

在 ESP32-S3 上对 **SeekAudio AEC** 与 **esp-sr AFE AEC** 进行同条件 A/B 对比评测的完整工程：同一块板、同一段素材、同一套自动化报告工具，四个配置依次运行，结果可一键复现。

> 💡 **推广期福利**：SeekAudio AEC 现开放免费授权，首批接入团队/个人欢迎[联系我们](https://www.seekaudio.cn/)。

## 核心结果速览

以下为多样本平均数据（ESP32-S3 @240 MHz，16 kHz，32 ms 帧，微软 AEC Challenge 数据集）：

> **A1** = SeekAudio AEC + WebRTC NS　**A2** = SeekAudio AEC + AI 降噪
> **B1** = esp-sr FD-AEC + ns_pro（基线；ns_pro 即 esp-sr 集成的 WebRTC NS）　**B2** = esp-sr FD-AEC + NSNet2（基线）
> A1/B1 同为 WebRTC NS 降噪档、A2/B2 同为 AI 降噪档，两两对位公平。

| 指标 | A1 | A2 | B1（基线） | B2（基线） |
|---|---|---|---|---|
| CPU 平均负载 | **28.1%** | **37.8%** | 60.5% | 73.2% |
| 实时率 RTF（越高越好） | 3.56× | 2.64× | 1.65× | 1.37× |
| 相对基线算力节省 | **约 54%** | **约 48%** | — | — |
| 远端单讲 ERLE（dB，越高越好） | **21.5** | **29.4** | 9.7 | 17.8 |
| 残余回声（dBFS，越低越好） | **−46.6** | **−54.5** | −34.8 | −42.9 |
| AECMOS FE-ST Echo（回声抑制感知） | **4.04** | **4.04** | 3.10 | 3.62 |
| AECMOS NE-ST Other（近端自然度） | 3.46 | 3.21 | 3.68 | 3.77 |
| AECMOS DT Echo（双讲回声抑制） | **4.19** | 4.25 | 3.86 | 4.26 |
| AECMOS DT Other（双讲自然度） | 4.09 | 3.74 | 4.09 | 4.16 |
| AECMOS 综合（1–5，越高越好） | **3.85** | 3.80 | 3.48 | 3.77 |
| 内部 SRAM（KB） | 75.0 | 192.5 | 12.4 | 21.1 |
| PSRAM（KB） | 192.7 | 192.7 | 182.9 | 520.2 |
| Flash 模型分区（KB） | — | — | — | 1024 |

指标含义、逐条分析与 AECMOS 分项取舍说明见解决方案文章（与本表逐格一致）。

## 📚 文档导航

| 文档 | 中文 | English |
|---|---|---|
| 📄 解决方案文章（架构 / 实测 / 分析） | [docs/article](docs/article/README.md) | [EN](docs/article/README_EN.md) |
| 🧪 测试用例 ×10（主观 + 客观双重评估） | 见下方[用例索引](#-测试用例索引) | see index below |
| 📊 完整评测报告 v1.0 | [中文版](evaluationReport/SeekAudio_AEC_评测报告_v1.0_2026-07.txt) | [EN](evaluationReport/SeekAudio_AEC_Evaluation_Report_v1.0_2026-07.txt) |
| 🛠 报告工具使用说明 | [中文版](tools/aec_report_使用说明.txt) | [EN](tools/aec_report_user_guide_EN.txt) |

## 四个被测配置

| 配置 | 组成 | 说明 |
|---|---|---|
| A1 | SeekAudio AEC + WebRTC NS | 被测方案，传统降噪档 |
| A2 | SeekAudio AEC + AI 降噪 | 被测方案，AI 降噪档 |
| B1 | esp-sr FD-AEC + ns_pro | 基线，传统降噪档（ns_pro 即 esp-sr 集成的 WebRTC NS） |
| B2 | esp-sr FD-AEC + NSNet2 | 基线，AI 降噪档 |

四个配置共用同一线性前端输入（near.wav / far.wav），依次在同一次启动中运行，各自输出一个 wav。对比基线组件精确锁版：`esp-sr==2.4.5`、`esp-dsp==1.8.0`（见 `main/idf_component.yml`），B 组采用 esp-sr 默认内存布局。

## 🧪 测试用例索引

10 个用例覆盖全场景、长双讲、纯回声、走动时变路径、密集交替双讲等类型，每例含标注波形图、可下载试听的原始音频与完整自动化报告：

| # | 用例特征 | 中文 | English |
|---|---|---|---|
| 1 | 回声 / 近端 / 双讲全场景对比 | [中文](docs/cases/case1/README.md) | [EN](docs/cases/case1/README_EN.md) |
| 2 | 长双讲样本：收敛速度与双讲残余对比 | [中文](docs/cases/case2/README.md) | [EN](docs/cases/case2/README_EN.md) |
| 3 | 走动双讲样本：基线出现回声放大（负 ERLE） | [中文](docs/cases/case3/README.md) | [EN](docs/cases/case3/README_EN.md) |
| 4 | 双讲样本：开头段收敛速度对比 | [中文](docs/cases/case4/README.md) | [EN](docs/cases/case4/README_EN.md) |
| 5 | 纯回声难样本：残余量级对比 | [中文](docs/cases/case5/README.md) | [EN](docs/cases/case5/README_EN.md) |
| 6 | 纯回声长样本：残余位置逐点对比 | [中文](docs/cases/case6/README.md) | [EN](docs/cases/case6/README_EN.md) |
| 7 | 走动+极低回声电平：又一例基线回声放大 | [中文](docs/cases/case7/README.md) | [EN](docs/cases/case7/README_EN.md) |
| 8 | 双回声段样本：开头段可闻差异 | [中文](docs/cases/case8/README.md) | [EN](docs/cases/case8/README_EN.md) |
| 9 | 密集交替双讲：本组差距最大的用例之一 | [中文](docs/cases/case9/README.md) | [EN](docs/cases/case9/README_EN.md) |
| 10 | 密集双讲：基线 FE 感知分崩盘的用例 | [中文](docs/cases/case10/README.md) | [EN](docs/cases/case10/README_EN.md) |

## 🚀 快速复现

**硬件要求**：已在 **ESP32-S3-BOX-3** 上验证；任何 **16 MB Flash**（分区表合计约 14.1 MB，8 MB 模组无法烧录，见 `partitions.csv`）且带 PSRAM 的 ESP32-S3 模组均可。

**软件环境**：ESP-IDF 5.3 – 5.5（已验证）；PC 端 Python 3 + `pip install numpy librosa onnxruntime littlefs-python`。

```bash
# 1. 编译
idf.py fullclean
idf.py set-target esp32s3
idf.py build

# 2. 将测试素材打包为 littlefs 镜像（2304 x 4096 = 0x900000，与 storage 分区大小严格一致）
python -m littlefs create --block-size 4096 --block-count 2304 fs_files/ fs.img

# 3. 一次性烧写 bootloader / 分区表 / 应用 / 素材镜像 / esp-sr 模型
#    （-p 按实际串口：Windows 为 COMx，Linux 为 /dev/ttyUSBx）
esptool.py -p COM3 -b 921600 write_flash 0x0 build/bootloader/bootloader.bin 0x8000 build/partition_table/partition-table.bin 0x10000 build/seekaudio_aec_test.bin 0x410000 fs.img 0xD10000 build/srmodels/srmodels.bin

# 4. 运行并观察（四配置顺序执行，输出 wav 写入 littlefs；结束后把串口日志保存为 log.txt）
idf.py -p COM3 monitor

# 5. 读回结果并解包，得到 a1/a2/b1/b2.wav
esptool.py -p COM3 read_flash 0x410000 0x900000 fs_out.img
python -m littlefs extract --block-size 4096 fs_out.img results/

# 6. 汇齐报告输入并生成报告：
#    results/ 中应有解包出的 near/far/a1/a2/b1/b2.wav，再放入两样东西——
#    (a) 第 4 步保存的串口日志 log.txt（算力/内存/延迟等设备端数据全部来自它，缺失则报告只剩离线音频指标）
#    (b) AECMOS 打分模型（缺失则跳过感知评分一节）
cp tools/Run_1663915512_Stage_0.onnx results/
cd results
python ../tools/aec_report.py --echo 0:10 --near 10:26 --dt 26:36
```

常用开关（见 `main/bench_config.h`，均可 `idf.py -D<宏>=0/1` 覆盖）：`RUN_A1/RUN_A2/RUN_B1/RUN_B2` 单独启停某配置；**B2 需要 model 分区已烧写 esp-sr 模型（srmodels），未烧写时请 `-DRUN_B2=0`**。

## 📁 目录结构

```
components/seekaudio_aec/   SeekAudio AEC 库（专有二进制 + 公开头文件）
main/                       评测程序（四配置调度、计时、littlefs 读写）
fs_files/                   测试素材（near.wav 麦克风信号 / far.wav 远端参考）
output_dir/case1..case10/   10 个测试用例的原始输出（素材 / 四路输出 / 日志 / 双语报告）
evaluationReport/           完整评测报告（中 / 英）
tools/                      aec_report.py 报告工具（中 / 英）+ AECMOS 模型
docs/                       解决方案文章与测试用例（中 / 英）
partitions.csv              分区表（storage=littlefs 素材与输出，model=esp-sr 模型）
```

## ⚖️ 公平性说明

- **B 组保持 esp-sr 官方默认内存布局**（主要缓冲位于 PSRAM），未做任何不利于基线的改动；对比组件精确锁版 `esp-sr==2.4.5`、`esp-dsp==1.8.0`。
- 代码中保留宏 **`B_AEC_INTERNAL_SRAM`**（`main/fd_aec_backend.cpp`，默认 0）：打开后 B1/B2 的关键缓冲改入内部 SRAM，实测算力占用约可降低 15% / 10%，但内部 SRAM 占用将飙升至约 130 KB / 200 KB 以上，且算力仍远远高于 SeekAudio 配置——属于以稀缺内部 SRAM 换少量算力的得不偿失配置，因此默认关闭。欢迎自行 `idf.py -DB_AEC_INTERNAL_SRAM=1 build` 复测验证，结论不会反转。
- **评测库基线**：本仓库全部报告与文档数据基于提交 [`ca75b3d`](https://github.com/seekaudio/seekaudio_aec_test/commit/ca75b3dae9f4d831fc60ac6ada16774ce2ec3429) 中的 `libseekaudio_aec.a` 测得（可 `git checkout ca75b3d` 严格对齐复现环境）；此后对库的任何优化不会体现在既有报告中，除非报告注明重新测试。

## 许可

仓库中的测试代码与文档以 MIT 许可发布；`components/seekaudio_aec/lib/` 下的 `libseekaudio_aec.a` 为 SeekAudio 专有二进制，仅授权评估用途，详见 [LICENSE](LICENSE) 与 [components/seekaudio_aec/LICENSE.txt](components/seekaudio_aec/LICENSE.txt)。

## 🎁 推广期免费授权

SeekAudio AEC 正在推广期，**目前可免费授权使用**。欢迎愿意“吃第一个螃蟹”的团队或个人联系获取授权 —— 你的早期反馈，我们会认真对待，并优先支持。

## 联系

商务合作与完整版授权：[https://www.seekaudio.cn/](https://www.seekaudio.cn/)
