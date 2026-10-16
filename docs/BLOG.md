# 从真实 ALOHA 数据出发：搭建机器人多模态轨迹处理管线 TrajGuard

一条机器人示范轨迹，除了相机画面，还包含关节状态、动作及其他采集字段。把 HDF5 读出来只是第一步：哪些轨迹可以保留、图像是否被改变、处理用了什么规则、中断后能不能继续，都需要在数据准备阶段解决。

本文以真实 ALOHA 的 episode_0 和 episode_1 为例，介绍 TrajGuard 的实现和成果。两条轨迹合计约 284 MB，包含 4000 个时间步与三路相机共 12000 帧图像，最终得到标准化 HDF5 成品和可追溯的处理清单。

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