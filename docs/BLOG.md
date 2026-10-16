# 机器人多模态数据工程实战：从解析、清洗、对齐到重标注与真实 ALOHA 验证

一条机器人示范轨迹，除了相机画面，还包含关节状态、动作及其他采集字段。把 HDF5 读出来只是第一步：哪些轨迹可以保留、图像是否被改变、处理用了什么规则、中断后能不能继续，都需要在数据准备阶段解决。

本文以真实 ALOHA 的 episode_0 和 episode_1 为例，介绍 TrajGuard 的实现和成果。两条轨迹合计约 284 MB，包含 4000 个时间步与三路相机共 12000 帧图像，最终得到标准化 HDF5 成品和可追溯的处理清单。

## 工程总览：从原始轨迹到可检查的成品

整个工程围绕视觉、机器人状态、动作和语言指令四类数据组织，既有用于理解完整链路的模块化演示，也有用于真实样本处理的 TrajGuard 命令行入口。

```text
HDF5 轨迹
   ↓
解析图像、状态、动作和指令
   ↓
运动规则过滤 → 不通过的样例与原因
   ↓
连续状态 / 离散动作重采样
   ├── 演示：首尾关键帧 → 模拟语义重标注 → clean_data
   └── 真实处理：压缩帧保留 → 标准化导出 → 来源清单与审核队列
   ↓
成品检查 / 视频预览 / HTML 质量页
```

### 数据解析与视频预览

`bridge_parser.py` 根据 HDF5 字段选择图像、状态和动作，识别 agentview_image、images0、images/top 等约定路径；data 组下取第一条 demo。其 export_to_mp4 接口接受已解码 RGB 像素序列，转为 OpenCV 使用的 BGR 后写入视频。

真实样本使用 cam_high、腕部相机和 JPEG 编码数组，需要由适配层识别。TrajGuard 的 adapters 模块支持多 episode、多相机；历史复现脚本 reproduction/adapt_real.py 展示了单路 JPEG 解码适配。本文实际处理采用保留编码的路径，避免整段提前展开。视频播放帧率与采集时间戳分别处理。

### 运动规则过滤

`kinematic_filter.py` 演示三个检查：最短轨迹长度、首尾状态的 L2 距离、相邻帧变化的最大值。最后一项计算的是帧间差，并未除以时间，不能直接解释为物理速度。首尾距离也可能将正常往返轨迹判成静止。

真实处理入口采用累计运动量和数值有效性检查，并在时间、单位明确时支持速度阈值。这样可以保留运动过滤这一环节，同时让每个检查对应可解释的条件。

### 多模态对齐与插值

`time_sync.py` 演示状态和连续动作的线性插值，以及末列夹爪动作的最近邻插值。其时间轴由帧数和目标帧率构造，等帧数时直接返回；original_robot_hz 参数未参与计算。`time_sync_show.py` 用 50 个机器人采样点和 30 个相机采样点展示该过程。

TrajGuard 的 alignment 模块进一步区分记录时间戳、用户假定频率和仅索引配对，在共同时间覆盖范围内重采样，并支持离散动作前值保持。本文真实样本使用的是索引配对，不能用它来证明 50 Hz 到 30 Hz 的实测同步效果。

### 语义重标注与审核

`vlm_relabel.py` 包含首尾关键帧提取、PIL 图像转换和任务描述 prompt，要求描述对象、颜色及空间关系变化。当前离线分支随机返回预设句子，真实 API 分支的客户端与推理调用仍是注释占位，填写 API Key 不能直接完成推理。

因此，这部分展示了重标注接口和数据流。TrajGuard 的 labels 模块提供另一项实际能力：生成候选模板，检查标签引用的轨迹、来源签名和审核状态，保留原始指令。接入外部模型后可以把输出交给审核流程，但当前实验没有评价真实 VLM 的描述质量。

### 多进程调度与成品检查

`main_pipeline.py` 以文件为单位创建进程池，在每个任务中执行解析、质检、重采样、模拟重标注和 HDF5 落盘。`inspect_clean_data.py` 检查其 images、qpos、actions、instruction 字段。

TrajGuard 的 pipeline 与 storage 模块支持配置并发数、单轨迹故障隔离、原子写入，以及通过输入和成品哈希验证断点恢复。其输出格式与演示入口不同，使用质量页和清单管理结果。

完整演示可在项目根目录运行：

```bash
python -m pip install -e ".[test,benchmark]"
python -m pip install scipy opencv-python Pillow tqdm
python generate_test_cases.py
python time_sync_show.py
python main_pipeline.py
python inspect_clean_data.py
```

生成器会写入 test_data 下的样例；主入口固定读取 test_data，输出到 clean_data，标签属于模拟输出。需要预览时，调用 VLADatasetParser.export_to_mp4；具体命令见 [README](../README.md)。下面使用真实数据处理入口展示整个工程目前可验证的成果。

## 一、先看原始数据里有什么

数据来自[原项目博客](https://blog.csdn.net/2303_77547168/article/details/158650625)链接的[公开数据目录](https://drive.google.com/drive/folders/1vhKa4tNPfMkeK7SW86vKorb39epTYW39)。两份文件的属性都是 sim=false、compress=true。

```text
原始 episode.hdf5
├── action                       (2000, 14)
├── base_action                  (2000, 2)
├── compress_len
└── observations/
    ├── qpos                     (2000, 14)
    ├── qvel                     (2000, 14)
    ├── effort                   (2000, 14)
    └── images/
        ├── cam_high
        ├── cam_left_wrist
        └── cam_right_wrist
```

每路相机各有 2000 帧，保存带填充的 JPEG 编码字节。episode_0 的单路形状为 (2000, 23276)，episode_1 为 (2000, 23884)；第二维是编码存储长度，并非图像宽度。

文件没有时间戳。本次按相同帧索引配对状态、动作和图像，在输出中标记 index_only，让下游知道采用了什么对应关系。帧数相同并不意味着已验证物理时间同步。

## 二、把处理步骤串起来

```text
扫描 HDF5 → 解析各 episode 和相机 → 规则质检
                                   ↓
                         时间重采样 / 索引配对
                                   ↓
                      分块写入 HDF5 + 来源信息
                                   ↓
                       manifest + HTML 质量页
```

解析层支持 ALOHA 和 robomimic 数据组织，状态、动作、相机通过统一结构进入后续流程，减少对单一样例字段布局的依赖。

质检层检查空轨迹、短轨迹、NaN/Inf 和累计运动量。累计运动量使用相邻状态变化总和，区分“完全没动”和“运动后回到起点”。时间、单位和检查列明确时，还可以配置速度阈值；本次缺少时间信息，没有启用速度阈值。

输入提供时间戳时，时间模块取共同覆盖区间再重采样，连续量使用线性插值，离散动作前值保持。无时间信息且各流长度一致时，则采用本次的索引配对路径。

## 三、为什么保留压缩图像

JPEG 如果提前全部展开为像素数组，会增加内存和磁盘开销。文件整理、基础数值质检和来源追踪无需先解码图像。

TrajGuard 分批复制编码字节。本次 chunk_frames=8，固定形状图像使用 HDF5 LZF 压缩写入，保留三路相机和来源索引，不进行 RGB/BGR 转换。

导出后独立逐块比较全部相机数据，并计算载荷 SHA256：两条轨迹的所有相机编码字节与源数据一致。状态、动作统一输出数值类型，其值也逐项一致。这验证了导出数据保真，尚不包含逐帧解码质量检测。

## 四、处理成果是什么样

```text
processed/
├── episodes/<任务签名>.hdf5
├── manifest.json
├── review_queue.json
└── report.html

成品.hdf5
├── state                        # 状态
├── actions                      # 动作
├── instruction                  # 原始指令字段
├── images/                      # 三路相机编码数据
└── source_indices/              # 状态、动作和相机来源索引
```

文件属性保存来源与处理模式。本次没有时间戳，因此没有生成虚构时间轴。base_action、qvel、effort 等未纳入当前导出范围的内容保留在原文件中。

| 文件 | 输入大小 | 成品大小 | 时间步 | 相机帧数 | 质检结果 |
|---|---:|---:|---:|---:|---|
| episode_0 | 140.15 MB | 93.87 MB | 2000 | 6000 | accepted |
| episode_1 | 143.80 MB | 95.85 MB | 2000 | 6000 | accepted |
| 合计 | 283.96 MB | 189.73 MB | 4000 | 12000 | 2 条通过 |

采用十进制 MB。体积受字段选择与存储方式共同影响，不能直接解释为全量数据压缩收益。两条正常样本通过，也不能据此计算异常检测准确率。

打开 report.html 可以筛选轨迹状态、查看处理信息。manifest.json 保存当前任务成员、规则结果、签名与成品路径；下游从清单读取 accepted 列表，避免将历史配置遗留文件混入当前数据集。

## 五、实际跑起来有多快

测试机器为 Ryzen 7 5800H、约 16 GB 内存，运行 Windows 和 Python 3.12.4。对同一组数据交替运行 1、2 个工作进程，各重复 3 次，取耗时中位数；未清空文件缓存。

| 工作进程 | 管线耗时 | 含启动与报告的总耗时 | 单工作进程峰值 RSS | 进程树采样峰值 RSS |
|---|---:|---:|---:|---:|
| 1 | 1.452 s | 2.020 s | 55.02 MiB | 53.92 MiB |
| 2 | 1.405 s | 1.944 s | 53.70 MiB | 146.37 MiB |

管线耗时包含输入哈希、质检、导出和成品哈希；总耗时还包含 Python/工作进程启动及报告写入。下载和独立字节核验不计入这两项耗时。

两条轨迹的任务很小，双进程收益有限，同时增加进程树内存占用，因此这组数据用单进程就比较合适。单工作进程峰值来自生命周期统计；进程树 RSS 每 20 ms 采样，可能遗漏短峰值并重复计算共享页，两列口径不同。

开启 --resume 后得到 resumed=2、processed=0：校验源文件和成品后复用已有结果。恢复总耗时约 0.980 秒，其中管线耗时约 0.361 秒。输入、配置或成品变化时，签名和哈希校验决定是否重新处理。

完整记录见 [benchmark.json](assets/aloha-benchmark.json)，源文件大小与哈希见 [下载凭据](assets/aloha-download-receipts.json)。

## 六、在自己的电脑上运行

在项目根目录安装依赖，将两份源文件放到同级 data/aloha-blog/：

```bash
python -m pip install -e ".[test,benchmark]"
python -m trajguard run --input ../data/aloha-blog --output ../outputs/aloha-real/processed --config configs/aloha_blog.json --workers 1
```

结束后打开输出目录的 report.html。验证恢复时，在运行命令末尾加 --resume。Windows PowerShell 可用 `& 'D:\anaconda\python.exe'` 替换 python。

重现本文多轮实测：

```bash
python scripts/benchmark_real.py --input ../data/aloha-blog --output ../outputs/aloha-real --config configs/aloha_blog.json --repeats 3 --workers 1 2
```

脚本完成重复测量、逐块一致性检查和恢复验证。相同输入与配置复用同一组输出路径，避免为每轮保存一份大型成品。

## 七、下一步可以做什么

目前已经打通真实数据接入、基础质检、编码图像保留和可追溯导出。下一步可以加入人工标注异常的数据，评估误删率与召回率；接入训练格式导出器，验证整理后的数据能否稳定进入策略训练。项目已有离线标签审核接口，真实 VLM 标注及其质量评估留待后续开展。

项目参考 [VLA-Data-Pipeline](https://github.com/Escapist-coder/VLA-Data-Pipeline)，原始脚本和来源说明保留在仓库中，本文实现对应 trajguard/。