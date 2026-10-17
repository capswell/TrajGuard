# TrajGuard · 机器人多模态轨迹数据处理与质量管理

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![HDF5](https://img.shields.io/badge/Data-HDF5-orange)
![CPU](https://img.shields.io/badge/Runtime-CPU-green)

> 面向具身智能与 VLA 数据准备，覆盖轨迹解析、运动规则过滤、多模态重采样、语义标注审核、视频可视化和可追溯批处理。

## 项目简介

机器人示范数据包含视觉、状态、动作和语言指令。TrajGuard 将数据接入、质量检查、时间处理、标准化导出与结果审核组织为完整工作流，使每条输出轨迹都能追溯到来源文件、处理配置和源帧索引。

核心管线离线运行，无需 GPU 或 API Key。工程同时提供模块化流程演示、命令行批处理工具、数据生成与验证脚本。

**阅读入口：** [实现详解](docs/BLOG.md) · [数据约定](docs/DATA_CONTRACT.md)

## 功能概览

| 功能 | 实现 |
|---|---|
| 多模态解析 | 接入 ALOHA、robomimic 风格 HDF5，读取状态、动作、指令和多路相机 |
| 轨迹质量检查 | 长度、NaN/Inf、累计运动量、时间有效性，以及时间和单位明确时的速度检查 |
| 多模态重采样 | 共同时间范围内处理连续量与离散动作，记录时间来源和插值策略 |
| 图像存储 | JPEG 编码帧分块复制，支持原始像素及变长编码帧，保留相机来源索引 |
| 语义标注 | 首尾关键帧与 prompt 示例、候选标签生成接口、标签来源和审核状态校验 |
| 视频可视化 | RGB 像素序列导出 MP4，检查成品字段、形状和指令 |
| 并行处理 | 文件/轨迹级任务调度，可配置工作进程数，单轨迹失败隔离 |
| 断点恢复 | 输入与配置签名、成品 SHA256 校验、原子写入和任务清单 |
| 质量管理 | accepted/review/rejected/failed 状态、HTML 质量页和人工审核队列 |

语义重标注模块提供首尾帧与模拟输出演示；真实 VLM 客户端是待接入扩展点。离线标签审核可直接使用，原始指令独立保留。

## 系统架构

```mermaid
flowchart TD
    A[HDF5 轨迹数据] --> B[解析状态 / 动作 / 多相机 / 指令]
    B --> C[结构与数值质检]
    C --> D[时间重采样或索引配对]
    D --> E[分块导出与来源记录]
    E --> F[标准化 HDF5 与 manifest]
    C --> G[审核队列与 HTML 质量页]
    F --> H[离线候选标签与审核]
    B --> I[像素序列视频预览]
    I --> J[首尾关键帧与重标注接口]
    J -. 外部模型接入 .-> H
```

推荐使用 `python -m trajguard` 进行批处理。根目录的 `main_pipeline.py` 串联解析、过滤、重采样、模拟重标注和落盘，适合演示完整模块协作。两种入口的输出 schema 不同。

## 处理成果

| 原始数据 | 处理结果 |
|---|---|
| 不同 HDF5 字段布局 | 统一的 state、actions、images 与 instruction |
| 多相机编码图像 | 按相机保留编码字节及来源索引 |
| 时间信息可能缺失 | 显式区分记录时间、假定频率和索引配对 |
| 轨迹质量需要逐条检查 | 规则结果、状态分类和可筛选质量页 |
| 处理过程难以复查 | 来源哈希、配置、版本、签名和成品哈希 |
| 重复执行整批任务 | 校验已有成品后复用有效结果 |

已生成的 ALOHA 成品保留 cam_high、cam_left_wrist、cam_right_wrist 三路相机及 14 维状态/动作；导出图像编码字节、状态和动作数值通过一致性核验，恢复运行能够复用已完成任务。原始测量记录保存在 [实验记录](docs/assets/aloha-benchmark.json)。

```text
output/
├── episodes/<任务签名>.hdf5
├── manifest.json          # 当前成员、规则结果、签名与成品路径
├── review_queue.json      # 待人工检查的任务
└── report.html            # 可筛选质量页
```

成品导出支持的状态、动作和相机字段；其他源字段继续保留在原文件。下游从当前 manifest 的 accepted 列表读取成品。

## 快速开始

### 1. 安装

Python 3.10+，在仓库根目录执行：

```bash
python -m pip install -e ".[test,benchmark]"
```

### 2. 运行示例

```bash
python scripts/make_demo.py --output ../work/trajguard-demo
python -m trajguard run --input ../work/trajguard-demo --output ../outputs/trajguard-demo --config configs/synthetic.json --workers 1
```

打开 `../outputs/trajguard-demo/report.html` 查看结果。

### 3. 处理自己的数据

将 HDF5 文件放入仓库同级 `data/episodes/`，按数据语义调整配置：

```bash
python -m trajguard run --input ../data/episodes --output ../outputs/processed --config configs/default.json --workers 1
python -m trajguard run --input ../data/episodes --output ../outputs/processed --config configs/default.json --workers 1 --resume
```

输入和输出目录需分离。工作进程数通过 `--workers` 调整。ALOHA 示例配置为 `configs/aloha_blog.json`；时间戳路径、单位和动作列设置见 [数据约定](docs/DATA_CONTRACT.md)。

### 4. 候选标签与审核

```bash
python -m trajguard label-template --manifest ../outputs/processed/manifest.json --output ../outputs/processed/candidates.json
# 填写候选指令、来源和审核信息后执行
python -m trajguard labels --manifest ../outputs/processed/manifest.json --input ../outputs/processed/candidates.json --output ../outputs/processed/labels.json
```

标签状态包括 candidate、reviewed、uncertain。reviewed 需要审核人，VLM 来源需要 model 和 prompt_version；校验来源及结构，语义正确性由审核环节判断。

## 模块演示与视频预览

```bash
python -m pip install scipy opencv-python Pillow tqdm
python generate_test_cases.py
python time_sync_show.py
python main_pipeline.py
python inspect_clean_data.py
```

生成器写入 `test_data/`，主脚本固定读取该目录并输出 `clean_data/`，指令为模拟文本。其解析器接收约定字段的已解码图像；压缩 ALOHA 数据使用 TrajGuard 入口。

```bash
python -c "from bridge_parser import VLADatasetParser; p=VLADatasetParser('test_data/case1_perfect.hdf5'); p.extract_trajectory(); p.export_to_mp4('trajectory_preview.mp4')"
```

视频接口接受 RGB 像素，默认以 30 fps 播放；播放速率与采集时间语义分开管理。

## 工程目录

```text
.
├── main_pipeline.py       # 模块串联与进程池演示
├── bridge_parser.py       # 字段解析、MP4 导出
├── kinematic_filter.py    # 长度、位移、帧间变化检查
├── time_sync.py           # 线性与最近邻插值
├── time_sync_show.py      # 重采样示例
├── vlm_relabel.py          # 关键帧、prompt、模拟重标注
├── inspect_clean_data.py  # 演示成品检查
├── generate_test_cases.py # 合成正常/异常轨迹
├── trajguard/             # 命令行、解析、质检、对齐、存储、审核
├── configs/               # 处理配置
├── scripts/               # 数据生成、评估、性能测量
├── tests/                 # 回归测试
├── docs/                  # 实现文章、数据约定与实验记录
└── reproduction/          # 基线复现辅助工具
```

## 验证与性能设计

```bash
python -m pytest
```

测试覆盖时间边界、离散动作、异常数值、多轨迹解析、编码帧保真、损坏成品恢复及标签来源校验。真实 ALOHA 数据测量入口：

```bash
python scripts/benchmark_real.py --input ../data/aloha-blog --output ../outputs/aloha-real --config configs/aloha_blog.json --repeats 3 --workers 1 2
```

该脚本针对 ALOHA 索引配对导出进行测量与核验。分块读写控制图像缓冲量；有界任务提交控制并发积压；断点恢复避免重复导出。并发配置应根据磁盘带宽、轨迹长度和内存预算选择。

## 致谢

项目参考 [Escapist-coder/VLA-Data-Pipeline](https://github.com/Escapist-coder/VLA-Data-Pipeline)，原始脚本及 [上游说明](docs/UPSTREAM_README.md) 保留在仓库中。ALOHA 数据入口见 [公开数据目录](https://drive.google.com/drive/folders/1vhKa4tNPfMkeK7SW86vKorb39epTYW39)。