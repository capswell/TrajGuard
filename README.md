# TrajGuard

**可追溯的机器人轨迹数据质检与处理工具。** 面向 HDF5 演示轨迹，支持多 episode、多相机、时间重采样、规则质检、压缩帧保留和断点续跑。默认离线运行，不需要 GPU、API Key 或境外服务。

基于 [Escapist-coder/VLA-Data-Pipeline](https://github.com/Escapist-coder/VLA-Data-Pipeline) 的工程改造。上游 `0707ad7` 用于基线复现；原 Python 脚本保留，新工具由 `trajguard/` 独立实现。上游原说明见 [docs/UPSTREAM_README.md](docs/UPSTREAM_README.md)。能力与实验结果以新文档和测试为准。

## 实现范围

| 部分 | 新工具行为 |
|---|---|
| 适配 | ALOHA 风格根目录及 robomimic 风格 data/demo_*；所有 episode、多相机 |
| 语义 | 区分 joint_positions 与 eef_position；单位、检查列、离散动作列显式配置 |
| 质检 | 空/单帧、NaN/Inf、短轨迹、累计运动量、速度阈值、重复/乱序时间戳及时间覆盖 |
| 重采样 | 共同时间范围，不外推、不跨大缺口插值；离散动作前值保持 |
| 图像 | 不解码 JPEG；按批复制编码字节，保留来源帧索引，避免提前展开整段视频 |
| 批处理 | 可配进程数、最多 2×workers 个在途任务、单 episode 故障隔离 |
| 恢复 | 输入 SHA256+版本+配置决定任务签名；校验成品哈希后才跳过；每任务保存清单 |
| 审计 | 保留原指令、来源指纹、时间模式、插值策略、帧索引、规则和结果 |
| 报告 | 自包含 HTML 状态筛选页、JSON 清单、人工审核队列 |
| 标注 | 离线候选模板、来源签名及审核状态校验；不随机伪造标签，不覆盖原文 |

尚未实现 Zarr/RLDS、ROS、自动估计时钟偏移/漂移、四元数插值、关节周期展开、真实 VLM 推理或下游策略训练。图像编码字节保留不等于已验证可解码或视觉质量，标记为 encoded_payload_unvalidated。不能把任意姿态向量当作可直接线性插值的数据。

## 安装与演示

Python 3.10+；本机验证使用 Python 3.12.4。

```bash
python -m pip install -e ".[test]"
python scripts/make_demo.py --output ../work/trajguard-demo
python -m trajguard run --input ../work/trajguard-demo --output ../outputs/trajguard-demo --config configs/synthetic.json --workers 2
python scripts/evaluate_demo.py --truth ../work/trajguard-demo/ground_truth.json --manifest ../outputs/trajguard-demo/manifest.json --output ../outputs/trajguard-demo/evaluation.json
```

打开 `../outputs/trajguard-demo/report.html`。7 个受控样例预期：2 accepted、4 rejected、1 review。往返后回到起点的正常轨迹应通过，静止轨迹等待人工判断。这是受控回归验证，不是对真实数据的检测精确率。Windows 可使用明确的解释器，例如 `& 'D:\anaconda\python.exe' -m trajguard ...`。

## 处理自己的数据

```bash
python -m trajguard run --input /data/episodes --output /data/trajguard-output --config configs/default.json --workers 2
python -m trajguard run --input /data/episodes --output /data/trajguard-output --config configs/default.json --workers 2 --resume
```

输出目录必须在输入树之外。不默认所有相机是 30Hz，不默认末列是离散夹爪。路径、单位、时间和控制语义见 [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md)。

- recorded_timestamps：各流都有记录时间戳，并假设位于同一时钟域。
- assumed_rate：至少一个流来自用户显式指定的采样率，保留该假设。
- index_only：所有流无时间信息且长度一致，仅按索引配对，不称为时间对齐。
- 部分流有时间而另一些缺失时拒绝处理，不偷偷生成时间。

max_speed 使用检查列的单位/秒，必须声明 state_unit。checked_state_indices 可排除夹爪等不同量纲列，检查列应具有可比较的单位。无时间信息却配置速度阈值时拒绝处理。

退出码：0=工具完成（可能含 rejected/review）；1=存在文件/工作进程处理失败；2=调用/配置错误。是否有可用数据必须读取清单。

## 输出与恢复

```text
output/
  manifest.json          # 当前数据集成员、规则、耗时、签名与成品哈希
  review_queue.json      # review/rejected/failed 的人工检查入口
  report.html            # 可筛选报告
  episodes/*.hdf5        # accepted 产物，按签名命名
```

产物保留编码图像、重采样状态/动作、原始指令、目标/源时间轴和帧索引。**成员以当前 manifest 中 accepted 的 artifact 列表为准，不能直接 glob episodes。** 配置或输入变化会生成不同签名的产物，历史文件保留；重复实验需规划存储。

HDF5 临时文件关闭后原子替换，每个 episode 完成即原子写 manifest。恢复会重新读取输入/成品计算哈希，失败任务会重试。输出锁 .trajguard.lock 防止并发写入；硬终止后确认无活动任务再手动移除遗留锁。输入应为稳定快照。并发最优值受存储和数据分布影响，默认 1 个进程。

## 离线标注审核

```bash
python -m trajguard label-template --manifest ../outputs/trajguard-demo/manifest.json --output ../outputs/trajguard-demo/candidates.json
# 人工或外部 VLM 填写候选后：
python -m trajguard labels --manifest ../outputs/trajguard-demo/manifest.json --input ../outputs/trajguard-demo/candidates.json --output ../outputs/trajguard-demo/labels.json
```

状态为 candidate/reviewed/uncertain。reviewed 必须填审核人；VLM 候选必须记录模型和 prompt_version；过期/重复/非 accepted 任务引用被拒绝。校验只保证结构与来源，不判断描述正确，reviewed 是用户声明。执行后描述是否适合作为训练前指令需另行审核，候选不会覆盖原始指令。

## 测试与实验

```bash
python -m pytest
python scripts/benchmark.py --output ../outputs/trajguard-benchmark
```

覆盖时间偏移、因果保持、无交集、空/单帧、往返运动、状态列、JPEG 字节不变、变长帧、写入失败、损坏成品恢复、配置/输入变更、多 episode、多进程隔离和标签来源。

benchmark 用独立子进程比较 1/2/4 个 worker，并提供单 episode 全量 JPEG 展开的内存参考。它是小型纯色 JPEG，压缩率有明显偏向；RSS 是单 worker 生命周期峰值，不是池总内存；解码参考不执行同样的完整流程，不用于端到端加速比。本次小样本中单进程更快。真实性能、真实异常精确率/召回率、VLM 质量和策略收益需要后续独立实验。

## 来源与贡献

新实现集中在 trajguard/、tests/、configs/、scripts/。reproduction/ 是之前的基线工具，不是新入口。建议简历表述为“基于开源 Demo 的工程改造”，见 [docs/RESUME.md](docs/RESUME.md)。不要引用上游 50GB 或 5.4× 作为自己的结果。
