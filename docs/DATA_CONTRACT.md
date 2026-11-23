# 数据约定 v1

ALOHA 风格为根目录 episode；robomimic 风格为 data/demo_*，以下路径相对于 episode 组。

| 语义 | 支持路径 |
|---|---|
| 关节状态 | observations/qpos、obs/joint_positions、obs/robot0_joint_pos |
| 末端位置 | obs/robot0_eef_pos（仅位置，不含四元数） |
| 动作 | action、actions |
| 多相机 | observations/images/<camera> |
| 单相机 | obs/agentview_image、observations/images0 |
| 原始指令 | language_instruction、instruction（标量字符串） |
| 状态时间 | timestamps/state、observations/timestamps |
| 动作时间 | timestamps/action |
| 相机时间 | timestamps/images/<camera> |

状态/动作至少两帧、有限二维数值数组。不假设动作与状态同义或数值相等。相机为 `[N,H,W,3] uint8`、`[N,padded_bytes] uint8` 或 `[N] vlen(uint8)`。编码帧原样保存，此版本不验证解码。base_action、effort、qvel 等暂不导出，原件应保留。

单位和动作含义需确认，不靠维度推断，不默认夹爪是 0/1。图像通道未知时记 unknown；训练/可视化加载器应按已确认的 decoded_color_order 转换，避免红蓝颠倒。

## 配置语法示例

```json
{
  "state_unit": "rad",
  "checked_state_indices": [0, 1, 2, 3, 4, 5],
  "max_speed": 2.0,
  "state_timestamp_path": "custom/state_time_ms",
  "action_timestamp_path": "custom/action_time_ms",
  "camera_timestamp_paths": {"cam_high": "custom/camera_time_ms"},
  "timestamp_scale": 0.001,
  "reference_camera": "cam_high",
  "action_interpolation": "previous",
  "discrete_action_indices": [6],
  "chunk_frames": 4
}
```

这是语法示例，不是机械臂通用物理配置。timestamp_scale 对所有记录时间统一生效，混合单位应先标准化。采样率假设用 state_fps/action_fps/camera_fps 指定；相机共用 camera_fps，不同频率应提供各自时间戳。

不排序、去重或外推时间戳，不估计时钟漂移。相机前值采样不晚于目标时间且限制最大时间差。状态线性重采样，动作默认前值保持；离散列始终前值保持。共同时间范围外及大间隙内的目标帧被过滤。结果时间戳可能不均匀，训练加载器应处理时间间隙，不应默认固定帧率连续。

## 输出

```text
/state, /actions             重采样 float64 数组
/instruction                 原始 UTF-8 指令
/timestamps                  目标时间；index_only 时没有此字段
/images/<camera>             编码字节或原像素数组
/source_indices/state_previous
/source_indices/action_previous
/source_indices/images/<camera>
/source_times/state
/source_times/action
/source_times/images/<camera>
```

state_previous 是插值左侧索引，可结合原始时间轴重建右侧。属性包含 schema_version、provenance（源 SHA256、episode、配置、版本）、alignment、state_kind、state_unit；图像包含 storage_kind、decoded_color_order。源时间仅在可用时保存，帧映射总是存在。

这是 TrajGuard 自身 schema，不宣称可直接送入 LeRobot/ACT/OpenVLA。后续需要受测试的训练加载器或导出适配器。

## 可选机器人语义（不绑定模型或控制软件）

Config.state_semantics 与 action_semantics 为对象，缺省为空，表示未知。允许 representation、unit、coordinate_frame、rotation、gripper、time_interval、frequency、dimensions；dimensions 是逐维 name/unit 对象列表，提供时必须匹配矩阵维度。frequency 可以是正数或 unknown，它描述语义，不能代替 state_fps/action_fps 等实际时间轴配置。速度检查目前仍使用 state_unit 与 checked_state_indices，不自动从描述推导单位。

示例：

```json
{
  "state_semantics": {"representation": "joint_position", "unit": "rad", "coordinate_frame": "joint", "rotation": "none"},
  "action_semantics": {"representation": "joint_position", "coordinate_frame": "joint", "rotation": "none", "gripper": "unknown", "time_interval": "unknown"},
  "camera_color_orders": {"cam_high": "rgb"}
}
```

这是配置语法，不是 ALOHA/Franka 的已确认物理定义。声明带旋转的状态线性重采样或动作线性重采样会报 pose-aware interpolation not implemented。动作 previous 保留原始指令值。未提供语义时保留诊断，不把结构质检通过解释为语义已验证。

成品属性 semantics 记录配置；provenance.source_metadata 记录源 episode 属性（字符串值）。DROID source_identity 可以跨预转换版本用于划分；不同来源必须保证稳定身份不会碰撞。逐相机颜色覆盖全局 decoded_color_order。

LeRobot 是独立导出接口，要求额外条件，参见 LEROBOT.md 和 COMPATIBILITY.md；核心 schema 本身不等于 LeRobotDataset。