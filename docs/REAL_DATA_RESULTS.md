# TrajGuard：真实 ALOHA 数据实测

使用博客链接的真实物理世界数据 episode_0.hdf5 与 episode_1.hdf5，文件属性均为 sim=false、compress=true。来源：https://drive.google.com/drive/folders/1vhKa4tNPfMkeK7SW86vKorb39epTYW39

## 数据与核验

| 指标 | 实测结果 |
|---|---:|
| 真实轨迹 | 2 条 |
| 状态/动作时间步 | 每条 2000，共 4000 |
| 状态、动作维度 | 各 14 维 |
| 相机 | cam_high、cam_left_wrist、cam_right_wrist |
| 相机图像帧 | 每条 6000，共 12000 |
| 原始文件合计 | 283957888 字节（283.96 MB） |
| 导出文件合计 | 189725877 字节（189.73 MB） |
| 基础质检 | 2 条通过 |
| 完整性检查 | 全部相机编码字节和源索引一致；状态、动作数值一致 |
| 断点恢复 | resumed=2、processed=0 |

图像保留 JPEG 编码，不解码、不改变颜色通道。导出仅包含支持的状态、动作、相机及来源信息；base_action、qvel、effort 等仍保存在原文件，因此文件大小差异不能表述为全量数据无损压缩率。

## 性能

Windows / AMD Ryzen 7 5800H（8 核 16 线程）/ 约 16 GB RAM / Python 3.12.4。1、2 个工作进程交替各运行 3 次，未清空文件系统缓存。下表耗时为中位数；不包含下载和独立字节核验。

| 工作进程数 | 管线耗时 | 含启动与报告的总耗时 | 单个工作进程峰值 RSS | 进程树采样峰值 RSS |
|---|---:|---:|---:|---:|
| 1 | 1.452 秒 | 2.020 秒 | 55.02 MiB | 53.92 MiB |
| 2 | 1.405 秒 | 1.944 秒 | 53.70 MiB | 146.37 MiB |

管线耗时包含输入哈希、质检、导出和输出哈希；总耗时还包含 Python/工作进程启动及报告写入。进程树 RSS 每 20 ms 采样，可能遗漏瞬时峰值并重复计算共享页，与单进程生命周期峰值口径不同。该两文件任务中双进程收益有限，建议默认单进程。

恢复运行管线耗时 0.361 秒，总耗时 0.980 秒；校验来源与成品后复用两条输出，没有重复处理。

原始数据没有时间戳，本次采用 index_only，不代表完成物理时间同步验证。两条正常样本通过不能推导异常检测准确率、召回率或大规模吞吐能力。

## 可放入简历的表述

**TrajGuard｜机器人多模态轨迹数据处理与质量检查工具**

- 构建面向机器人示范轨迹的数据处理流程，实现 HDF5 数据接入、规则质检、标准化导出、来源追踪及可视化质量报告。
- 在 2 条真实 ALOHA 轨迹上验证，覆盖 4000 个时间步、14 维状态/动作及三路相机共 12000 帧图像；采用分块读写保留 JPEG 编码，并逐块验证导出图像字节与状态/动作数值一致。
- 在 Ryzen 7 5800H、16 GB 内存环境下，对约 284 MB 输入进行 3 次单进程实测，端到端耗时中位数 2.02 秒，单进程峰值 RSS 约 55 MiB；实现哈希校验与断点恢复，重复运行成功复用全部 2 条结果。

以上性能数据限定于本次两文件、缓存未清空的测试条件。未开展 VLM 标注或策略训练。

## 文件位置与复现

桌面项目：C:\Users\12853\Desktop\TrajGuard\VLA-Data-Pipeline

原始数据：C:\Users\12853\Desktop\TrajGuard\data\aloha-blog

成品与 HTML 报告：C:\Users\12853\Desktop\TrajGuard\outputs\aloha-real\processed

在项目目录运行：

```powershell
& 'D:\anaconda\python.exe' scripts/benchmark_real.py --input ../data/aloha-blog --output ../outputs/aloha-real --config configs/aloha_blog.json --repeats 3 --workers 1 2
```

同目录 benchmark.json 包含所有原始试验记录、源结构、逐相机 SHA256 和代码提交号；download_receipts.json 记录源文件大小及 SHA256；hardware.json 记录机器信息。多轮运行复用同一份成品，不保存多份大型数据。