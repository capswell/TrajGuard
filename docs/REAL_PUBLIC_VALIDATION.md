# 真实公开样本端到端验证（2026-11-23）

本次实际下载并读取公开原件，未使用 fixture 代替真实数据。目标是文件转换、图像/数值正确性及 LeRobot 读取，不是模型效果或硬件评测。

## 结果

| 数据 | 输入 | TrajGuard | LeRobot 0.6.1 存储 | 实际读取 |
|---|---|---|---|---|
| ALOHA 博客公开原件 | episode_0/1，两条各 2000 帧、14 维状态/动作、三相机 | 两条 accepted，4000 帧 | H.264 / PyAV，4000 帧、约 111.09 MB（含元数据） | state [2,14]；action [2,50,14]；三相机各 [2,3,480,640] |
| 官方 DROID debug RLDS | droid_100/1.0.0，r2d2_faceblur 的首分片，两条共 404 帧 | 两条 accepted，8 维状态/动作 | 图像模式，404 帧、约 99.69 MB（含元数据） | state [2,8]；action [2,50,8]；三相机各 [2,3,180,320] |

ALOHA 导出约 530.15 秒，DROID 导出约 38.34 秒。它们是本机各一次功能验证，格式、分辨率和规模不同，不可推导加速比或性能提升。当前 seed=42 的少量样本恰好全部属于 train，没有验证集指标。

两组检查均成功：

- 所有源状态/动作与 TrajGuard 成品数值一致。
- LeRobot 首、中、末采样帧的状态、任务、50 步动作和 padding mask 正确；末尾保持最后动作，不跨 episode。
- 采样帧的所有相机载荷与源一致，再比较解码后的 LeRobot 图像。ALOHA 三路视频共 12000 帧全量解码通过，每路各 4000 帧；DROID 图像模式误差为 0；ALOHA H.264 有损编码的最大采样 RGB MAE 为 2.194/255（阈值 12）。不声称视频像素无损。
- DROID 另外逐步比较官方 TFDS 与导入 HDF5：404 帧的全部状态、关节位置命令、夹爪、三路图像及任务指令一致。
- 完整导出目录的 --resume 校验成功。代码改变后旧导出签名被拒绝，使用新目标重新验证。
- 回归测试：LeRobot 独立环境 70 项通过，含图像与 H.264 视频模式。真实样本是独立脚本执行的集成核验，不计入这 70 项。

## 来源、时间与语义依据

ALOHA 原件来自上游博客的 Google Drive 目录，文件 ID、大小和 SHA256 见 [下载凭据](assets/public-validation/receipts.json)。两份 SHA256 与历史下载一致。

参考采集代码：[Mobile ALOHA real_env](https://github.com/MarkFzp/mobile-aloha/blob/main/aloha_scripts/real_env.py)、[record_episodes](https://github.com/MarkFzp/mobile-aloha/blob/main/aloha_scripts/record_episodes.py)。状态/动作解释为双臂每侧六关节加一个原生归一化夹爪值；关节 rad，夹爪保持原生无量纲数值，不裁剪、不换成米。参考实现将夹爪定义为 0 闭合、1 张开，但样本可轻微超出区间，不据此静默截断。

原件没有记录时间，50 Hz 明确是参考采集实现的假设，不是样本采集时钟测量。观察与动作按相同索引配对，物理控制延迟未验证。未导出 base_action，不作为完整移动底盘训练数据。缺少原始语言标注，使用明确带有“manual coarse description for format validation”标记的粗略任务描述；不作为精细语言标签质量验证。

ALOHA 颜色另与原版视频的 episode_0 首、中、末帧核对。红蓝校正后参考误差降低，具体记录见 [颜色核验](assets/public-validation/aloha-color-check.json)。该设置是样本特定解码语义，不能自动用于所有 ALOHA 数据。

DROID 来自 [官方公开目录说明](https://droid-dataset.github.io/droid/the-droid-dataset)，本次实际发行名为 r2d2_faceblur/1.0.0。只下载首分片 27488816 字节与元数据，不修改完整数据集 split/shard 元数据；TFDS 使用 train[:2] 精确读取该分片，避免请求未下载的其他分片。

DROID 保留 action_dict/joint_position[7] 与 gripper_position[1]，不使用通用 action 向量、不变换为 delta 或速度。15 Hz 是 [OpenPI 官方 DROID 频率约定](https://github.com/Physical-Intelligence/openpi/blob/main/docs/norm_stats.md)；发行 schema 没有记录时间戳。模型若需要关节速度动作，必须另外转换或选择相应动作字段，本验证不意味着匹配默认 π₀.₅ 动作空间。

## 完整命令

Python 3.12 独立环境，仓库根目录：

```bash
python -m pip install -e ".[test,lerobot,droid]"
python scripts/download_public_samples.py --output ../data/public-validation
# 如需代理：在下载命令加 --proxy http://HOST:PORT

python -m trajguard run --input ../data/public-validation/aloha --output ../outputs/public-validation/aloha-qc --config configs/aloha_blog.json
python -m trajguard export-lerobot --manifest ../outputs/public-validation/aloha-qc/manifest.json --config configs/lerobot_aloha_public.json --output ../outputs/public-validation/aloha-video
python scripts/check_lerobot.py --root ../outputs/public-validation/aloha-video --horizon 50
python scripts/audit_public_export.py --root ../outputs/public-validation/aloha-video --manifest ../outputs/public-validation/aloha-qc/manifest.json --report ../outputs/public-validation/aloha-audit.json

python -m trajguard import-droid --builder-dir ../data/public-validation/droid/1.0.0 --output ../data/public-validation/droid-hdf5 --limit 2
python scripts/audit_droid_source.py --builder-dir ../data/public-validation/droid/1.0.0 --hdf5-dir ../data/public-validation/droid-hdf5 --report ../outputs/public-validation/droid-source-audit.json
python -m trajguard run --input ../data/public-validation/droid-hdf5 --output ../outputs/public-validation/droid-qc --config configs/droid_public.json
python -m trajguard export-lerobot --manifest ../outputs/public-validation/droid-qc/manifest.json --config configs/lerobot_droid_public.json --output ../outputs/public-validation/droid-images
python scripts/check_lerobot.py --root ../outputs/public-validation/droid-images --horizon 50
python scripts/audit_public_export.py --root ../outputs/public-validation/droid-images --manifest ../outputs/public-validation/droid-qc/manifest.json --report ../outputs/public-validation/droid-audit.json
```

实际本机最终 DROID 成品目录为 droid-images-verified，其他命令相应替换即可。示例均使用新目标目录；已有完整目录使用 --resume，失败目录保留诊断。

依赖实测：Windows、Python 3.12.4、torch 2.11.0 CPU、LeRobot 0.6.1、PyAV 15.1.0、TensorFlow 2.20.0、TFDS 4.9.10。TorchCodec 缺少 FFmpeg shared DLL 时，读取显式使用 PyAV；H.264 写入也走 PyAV，不依赖系统 ffmpeg 命令。

## 仍待验证

π₀.₅ 模型 processor、预训练归一化、前向/反向、保存重载和实际效果；实验室 Franka 自采与真机；真实 recorded timestamps 跨传感器同步；其他 DROID 发行版本与原始 H5+外部 MP4。DROID 是公开 Franka 案例，不代表所有 Franka 控制器和采集格式均已兼容。

大文件只保存在仓库同级 data/outputs/work 中。仓库只提交配置、验证脚本与小体积证据；数据使用条件仍按原数据源处理。