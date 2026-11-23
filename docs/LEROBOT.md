# LeRobot 0.6.1 接入

最新真实样本验证：ALOHA 4000 帧 H.264、官方 DROID 404 帧图像模式均已通过实际读取及未来动作检查。参见 [真实验证记录](REAL_PUBLIC_VALIDATION.md)，下方日期记录保留历史阶段的验证情况。

## 当前范围

入口：`python -m trajguard export-lerobot --manifest MANIFEST --config CONFIG --output ROOT`。
导出通过 LeRobot 0.6.1 的 create/add_frame/save_episode/finalize 公开接口完成。使用独立 Python 3.12 环境：

```powershell
python -m venv ../lerobot-env
../lerobot-env/Scripts/python -m pip install "lerobot[dataset]==0.6.1" h5py pytest
```

普通安装仍无需 LeRobot；只有导出需要该可选依赖。示例配置 configs/lerobot_fixture.json 仅定义合成 fixture，不得套用到真机。

## 从原始 HDF5 到训练 batch

在已安装依赖的环境、仓库根目录执行：

```bash
python scripts/make_demo.py --output ../work/lerobot-demo
python -m trajguard run --input ../work/lerobot-demo --output ../outputs/lerobot-qc --config configs/synthetic.json
python -m trajguard export-lerobot --manifest ../outputs/lerobot-qc/manifest.json --config configs/lerobot_fixture.json --output ../outputs/lerobot-dataset
python scripts/check_lerobot.py --root ../outputs/lerobot-dataset --horizon 50
```

真实 HDF5 替换输入目录及处理配置，导出配置必须逐项填写：camera 源名到训练名映射、colors（解码后 rgb/bgr）、state_dimensions/action_dimensions（逐维 name/unit）、机器人类型、动作 representation/coordinate_frame/rotation/gripper/time_interval/control_frequency。缺失指令仅允许人工确认的 fallback_instruction。index_only 必须提供 index_fps_basis，说明 fps 的依据，不能将其称为记录时间。导出不自动改动动作表示或归一化。

## 时间与动作块

导出要求固定间隔。较大间隔切成独立 episode，少于两帧片段丢弃；较小间隔或抖动不满足 tolerance 时拒绝，不对姿态自动线性插值。源时间与导出帧映射保存在 trajguard_export.json；LeRobot 帧时间是片段内从零起算的 i/fps。

check_lerobot.py 实际构造 action 的 50 步 delta_timestamps，并检查片段末尾重复最后动作及 action_is_pad。训练损失必须正确使用 padding mask。此导出器不进行 SO(3) 或 SE(3) 转换。

split 根据源内容 SHA256 + episode 标识、seed 进行确定性哈希划分；同一原件的不同处理版本与片段在同一 split。修改原始文件字节会改变身份，跨格式重复数据需另行去重。split 保存在映射中，训练时必须通过 episodes 列表显式选择 train；默认 LeRobot 读取会读到所有划分。

LeRobot 写入器的统计量覆盖整份导出，不能直接用于 train/validation 实验归一化。导出器另存 trajguard_train_stats.json，包含 train 帧的 mean/std/min/max/q01/q99。训练必须显式连接 policy processor，当前尚未实现 processor 对接；空训练划分输出空统计量，必须停止训练。不要直接使用混合划分统计量。

## 失败及恢复

输出先写到 ROOT.incomplete，通过 finalize、真实 reader 帧数和首帧读取后才改为 ROOT。异常保留 incomplete 供诊断；不自动追加、不自动删除。重新运行请选择新目录。--resume 仅对签名相同且所有输出及输入成品哈希匹配的完整导出进行复用，不承诺逐 episode 的中断续写。

## DROID 支持范围

支持官方 RLDS/TFDS schema，经 TFDS builder 读取，转换为现有 HDF5 输入。未支持 trajectory.h5 + 外部 MP4 原始发行包。资料：

- https://droid-dataset.github.io/droid/the-droid-dataset
- https://github.com/Physical-Intelligence/openpi/blob/main/src/openpi/training/droid_rlds_dataset.py
- https://github.com/huggingface/lerobot/blob/v0.6.1/src/lerobot/datasets/lerobot_dataset.py

```bash
# 建议 Linux 独立环境安装 tensorflow、tensorflow-datasets
python -m trajguard import-droid --builder-dir /data/droid/1.0.1 --output ../data/droid-hdf5 --limit 2
python -m trajguard run --input ../data/droid-hdf5 --output ../outputs/droid-qc --config configs/default.json
```

字段：observation/joint_position[7]+gripper_position[1]；action_dict/joint_position[7]+gripper_position[1]。保留绝对关节位置命令，不使用通用 action 向量，不自动转换 delta。相机为 exterior_image_1_left、exterior_image_2_left、wrist_image_left，RGB。语言取 language_instruction，要求非空且整条一致。release schema 没有时间戳，保留 index_only；频率、夹爪量纲和命令时序需根据所用发行版确认后配置导出。

DROID 适配器已通过官方 r2d2_faceblur/1.0.0 首分片的两条真实轨迹验证；fixture 另用于回归测试。真实验证需下载官方 droid_100 调试包、指定包含 dataset_info.json 的 TFDS 版本目录，然后完成 import、质检、导出、check_lerobot 四步。缺失字段、变更指令、非完整 episode 会报错。转换一次载入一条 episode 图像，不适合超长轨迹；外部源身份属性已通过 source_metadata 贯穿到核心 provenance。

## Franka 最小采集约定

每个 HDF5 文件一条 episode，配置/元数据另存同名 JSON：

- episode_id（稳定 UUID）、instruction、任务成功标记、终止原因、采集软件提交和配置哈希。
- observations/qpos、action；每列定义、单位、关节名称；观测和实际发送控制指令分别记录。
- timestamps/state、timestamps/action、timestamps/images/<camera>：秒、严格递增、同一单调时钟域；跨设备记录时钟同步方法及误差。
- observations/images/<camera>：uint8 RGB 像素或编码载荷；声明编码器、解码后颜色顺序、相机序列号、尺寸、内外参版本。
- robot 型号/序列号、夹爪型号、控制器及模式、采集与控制频率、相机频率。
- action representation、基坐标系/工具坐标系、位置/速度/增量语义、旋转表示、夹爪开度或命令含义、命令对应时间区间及延迟。

现有解析器直接读取这些 HDF5 数据路径；其他元数据目前需保留 sidecar 并在导出配置中填写，尚未自动导入。关节位置路径不能存笛卡尔姿态并假称关节。型号、控制程序和遥操作设备确认后再定义对应映射与模型接口。

## 模型验证边界

数据 batch 检查不是 π₀.₅ 模型前向/反向验证。尚未验证 checkpoint、相机键、state/action padding、tokenizer 和 processor 的模型兼容性。确认这些配置后，可在已有 LeRobot 0.6.1 训练环境使用 lerobot-train 的 policy.path、dataset.repo_id、dataset.root、dataset.episodes、steps、batch_size 等参数运行短训；具体参数应以该环境 lerobot-train --help 与 checkpoint 配置为准。当前不提供未经运行验证的可执行真机训练承诺。
## 本机验证记录

2026-11-23：原有 52 项测试通过；新增时间/颜色/DROID fixture 测试后为 59 项通过。独立环境已安装 LeRobot 0.6.1、torch 2.11.0 CPU、NumPy 2.2.6。合成 HDF5 经质检后 2 accepted，导出 72 帧，并通过真实 LeRobotDataset 读取与 50 步未来动作块末尾 padding 检查。图像模式已验证；视频模式尚未验证。TorchCodec 缺少 FFmpeg shared DLL，实际回退 PyAV。

真实 ALOHA 原件已清理，当前未重新获取；14 维动作语义、任务指令、频率待确认，因此未冒充完成真实训练数据验证。未获得 DROID 真样本、模型权重或真机，未执行模型前向/反向、保存重载或闭环评测。

## 短训练命令模板（未执行）

以下参数已核对 0.6.1 的 DatasetConfig/TrainPipelineConfig。必须先完成相机键匹配、真实动作语义确认、训练划分与归一化 processor 对接，再替换 checkpoint 和 train episode 列表；该命令不适用于合成 fixture 的模型效果评估。

```bash
lerobot-train --policy.path=/models/pi05-compatible-checkpoint --dataset.repo_id=local/franka --dataset.root=/data/franka-lerobot --dataset.episodes='[0,1]' --dataset.video_backend=pyav --steps=20 --batch_size=1 --output_dir=outputs/pi05-smoke --wandb.enable=false
```

独立环境完整 pytest：60 项通过（包括真实 LeRobot writer/reader 集成）；基础环境：59 项通过、1 项因缺少可选 LeRobot 而跳过。集成 fixture 含双 episode、双相机，检查已存在目标拒绝、有效目标恢复和损坏目标拒绝。未验证视频写入模式、真实 DROID、真实 ALOHA 导出和 π₀.₅ 前向/反向。