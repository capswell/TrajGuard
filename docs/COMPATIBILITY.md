# 支持范围与兼容性

核心边界：输入适配器负责读取文件和字段映射；Episode 是单轨迹内部表示；Config 定义语义与规则；quality/alignment 处理数组与时间；storage 导出 TrajGuard schema；独立导出器从当前 manifest 的 accepted 成品读取。核心模块不导入 LeRobot、模型或控制软件。

## 输入

| 适配器 | 布局与字段 | 时间/图像 | 验证范围 |
|---|---|---|---|
| ALOHA 风格 HDF5 | 根组；observations/qpos、action(s)、observations/images/*、instruction/language_instruction | timestamps/state、action、images/*；或显式频率；或等长 index_only。uint8 HWC RGB/BGR、填充编码字节或 vlen uint8 | 合成回归；此前真实公开 episode_0/1 完成基础处理及载荷保真。未验证真实 LeRobot 导出 |
| robomimic 风格 HDF5 | data/demo_*；obs/joint_positions、robot0_joint_pos 或 robot0_eef_pos；actions；obs/agentview_image | 同一时间规则；同一支持的图像形式 | 多 demo 合成回归；不等于支持所有 robomimic 发行版 |
| images0 兼容路径 | observations/images0，配合支持的状态/动作路径 | 同上 | fixture 路径支持，不宣称完整 BridgeData V2/RLDS 支持 |
| DROID RLDS/TFDS | import-droid 将官方 observation/joint_position+gripper_position、action_dict/joint_position+gripper_position 映射为 8 维；三路 left RGB；language_instruction | 发行 schema 无记录时间；index_only，频率需用户确认 | 官方字段 schema fixture 已测；TFDS 真实数据未测 |
| DROID 原始 H5+MP4 | 未实现 | 外部视频及时间需专用读取 | 计划支持 |
| Franka 自采 | 按 DATA_CONTRACT HDF5 约定可接入；型号/控制器由采集方声明 | 不默认控制频率、姿态或夹爪单位 | 数据约定已提供；真实硬件未测 |

缺失字段、部分流时间缺失、非法矩阵、未知相机配置均会诊断。图像字节保留并不等于验证可解码；解码验证在导出步骤执行。

## 输出与集成

| 格式 | 版本 | 已验证 | 尚待验证 |
|---|---|---|---|
| TrajGuard HDF5 | trajguard/1 | 多相机、帧映射、来源、原子写入、哈希恢复 | 与第三方训练器的直接兼容性不承诺 |
| LeRobotDataset | LeRobot 0.6.1，公开 create/add_frame/save_episode/finalize API | Windows CPU：图像存储、双 episode/相机、真实 reader、未来 50 步动作、padding、成品损坏拒绝 | 视频编码模式、真实 ALOHA/DROID 导出、其他 LeRobot 版本 |
| RLDS、Zarr 导出 | 无 | 未实现 | 计划项 |
| π₀.₅ / Franka 控制 | 下游案例 | 无本轮模型或硬件验证 | processor/相机键/归一化、训练、部署、闭环评测 |

测试来源：tests/conftest.py、scripts/make_demo.py 生成的 fixture 是程序构造数据；tests/test_droid.py 仅按官方文档构造字段，不含真实采集。历史 ALOHA 实测记录位于 docs/assets，来自上游博客链接的公开数据，不能推导异常检测准确率。

## 本轮优先级

1. 核心接口与语义诊断；基础安装不依赖 LeRobot。
2. CPU 最小流程、配置说明及可解释状态。
3. 独立 LeRobot 版本验证、来源/划分及失败恢复。
4. 真实公开发行包和视频模式验证。
5. 应用案例中的训练、模型与硬件验证。
## 2026-11-23 社区化验证

基础环境：67 项通过、1 项 LeRobot 可选集成跳过。独立 Python 3.12/LeRobot 0.6.1 CPU 环境：68 项通过。新增测试覆盖未知语义诊断、来源属性传播、逐相机颜色、语义维度、姿态插值拒绝、非法语义、导出前置条件及累计时间漂移。

README 合成最小流程已执行：7 条输入得到 2 accepted/4 rejected/1 review，恢复运行 processed=0、resumed=7；LeRobot 图像模式导出 2 episodes/72 frames，读取 action batch [2,50,3]、state [2,2]、image [2,3,48,64]，验证末尾 padding。安装元数据已构建并完成 editable 安装。本轮未运行远程 CI、Linux/TensorFlow 真样本、视频编码或模型/硬件验证。