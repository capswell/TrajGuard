# TrajGuard · 机器人多模态轨迹处理工具

面向社区的离线数据工具：读取机器人示范轨迹，执行规则质检与时间处理，导出带来源信息的成品，支持人工审核和可选训练格式转换。核心处理与具体机器人、控制软件及模型解耦。

[兼容性表](docs/COMPATIBILITY.md) · [数据约定](docs/DATA_CONTRACT.md) · [扩展指南](docs/EXTENDING.md) · [贡献方式](CONTRIBUTING.md) · [许可与数据状态](docs/RELEASE_STATUS.md)

## 快速开始：CPU 最小样例

Python 3.10+，在仓库根目录执行：

```bash
python -m pip install -e ".[test]"
python scripts/make_demo.py --output ../work/demo
python -m trajguard run --input ../work/demo --output ../outputs/demo --config configs/synthetic.json --workers 1
python -m trajguard run --input ../work/demo --output ../outputs/demo --config configs/synthetic.json --workers 1 --resume
```

打开 ../outputs/demo/report.html。7 个程序生成样例预期为 2 accepted、4 rejected、1 review；这些是逻辑测试样例。基础运行依赖 NumPy/h5py，生成 JPEG 演示额外使用 test 安装项中的 Pillow，无需模型、GPU 或真实采集设备。

## 工作流与边界

```text
来源读取 / 预转换 → Episode 内部表示 → quality / alignment
                                          ↓
                            TrajGuard HDF5 + manifest + HTML
                                          ↓
                             可选导出器 / 下游训练应用
```

- 输入适配器：ALOHA 与 robomimic 风格 HDF5；DROID RLDS 另用预转换入口。
- 内部约定：状态、动作、相机、指令和独立时间轴；不根据维度猜测机器人。
- 处理规则：长度、有限值、累计运动、配置的速度限制、时间覆盖及缺口。
- 输出格式：TrajGuard 自有 HDF5 schema，保存来源、配置、帧映射和签名。
- 独立集成：LeRobot 0.6.1 导出；π₀.₅、Franka 是下游应用案例。

## 配置与未知语义

参考 configs/default.json；state_semantics/action_semantics 支持 representation、unit、coordinate_frame、rotation、gripper、time_interval、frequency、dimensions。dimensions 中每列包含 name/unit。缺省语义保持 unknown 诊断，基础结构质检可以继续；需要具体语义的处理与导出会检查条件。

逐相机颜色通过 camera_color_orders 声明 rgb/bgr/unknown；时间用记录路径、显式采样率或等长 index_only。state_unit、checked_state_indices 和 max_speed 共同配置速度规则。当前通用线性插值不支持已声明的姿态旋转表示。详细例子见 [数据约定](docs/DATA_CONTRACT.md)。

## 报告与恢复

```text
output/
├── episodes/*.hdf5
├── manifest.json
├── review_queue.json
└── report.html
```

accepted 只表示通过配置规则，不代表完成任务或适合任意模型。review 表示需要结合任务复核；rejected 记录规则/数据条件不满足；failed 表示处理故障。manifest 保存原因、时间模式、语义诊断、配置与来源；成品保留源帧映射。下游只读取当前 accepted 成品列表。

核心恢复按输入、配置及版本签名，并校验成品哈希。数据与配置变化会产生新签名，失败任务可重试。图像在核心管线中保留编码、分块复制；解码有效性检查在有此需要的导出器中完成。

## 可选 LeRobot 集成

Python 3.12+ 独立环境：

```bash
python -m pip install -e ".[test,lerobot]"
python -m trajguard export-lerobot --manifest ../outputs/demo/manifest.json --config configs/lerobot_fixture.json --output ../outputs/demo-lerobot
python scripts/check_lerobot.py --root ../outputs/demo-lerobot --horizon 50
```

示例配置仅适用于上述合成样例。导出保留维度、任务关联和来源清单，固定间隔片段分开写入，训练统计仅根据 train 划分另存。训练时需显式选择 train episodes 并连接对应归一化 processor。已在真实 LeRobot 0.6.1 writer/reader 上验证图像模式、双相机、动作块与边界 padding；真实 ALOHA H.264 与官方 DROID RLDS 图像模式已验证；其他版本待验证。

[完整集成说明](docs/LEROBOT.md) 包含 DROID 范围、Franka 最小采集约定和未执行的 π₀.₅ 短训模板。它们不是运行核心工具的前提。

## 常见诊断

| 提示 | 处理方法 |
|---|---|
| Partial timing information | 为缺时间的流补录时间或显式采样率 |
| Unequal stream lengths without timestamps | 确认采集频率或提供时间轴，不通过补零假装同步 |
| semantics unspecified | 基础规则仍可用；训练导出前填写真实语义 |
| Explicit decoded color semantics / colors | 确认编码后解码颜色，不依据相机名称猜测 |
| Nonuniform or faster sampling | 上游明确重采样；大缺口会切成独立 episode |
| Target exists / incomplete | 保留失败目录诊断；用新目标重跑，完整目标用 --resume 校验复用 |
| Optional integration absent | 用 Python 3.12+ 安装 lerobot 可选项 |

## 测试与扩展

```bash
python -m pytest
```

基础测试使用合成 fixture；LeRobot 集成测试在安装可选依赖后运行。真实公开 ALOHA 的历史基础处理记录见 docs/assets；真实 DROID、真实 LeRobot 数据转换、视频编码及模型/硬件均分别标记验证状态。详见兼容性表。

原模块演示仍保留在根目录（main_pipeline.py、bridge_parser.py、kinematic_filter.py、time_sync.py、vlm_relabel.py 等）。它们展示解析、插值、视频和模拟重标注，推荐日常入口为 python -m trajguard。完整背景文章见 [BLOG.md](docs/BLOG.md)。

## 来源与发布状态

保留 [Escapist-coder/VLA-Data-Pipeline](https://github.com/Escapist-coder/VLA-Data-Pipeline) 原模块和 [原介绍](docs/UPSTREAM_README.md)。本仓库当前缺少完整项目许可证；第三方代码与样例授权范围尚待确认，不能把整仓库视为已获 MIT 授权。自有代码许可选择、样例再分发条件及发布待办见 [发布状态](docs/RELEASE_STATUS.md)。
## 真实公开数据验证

已完成 ALOHA 4000 帧和官方 DROID（Franka）404 帧到 LeRobot 0.6.1 的实际导出、读取及 50 步未来动作检查。数据来源、命令、频率假设和验证边界见 [真实验证记录](docs/REAL_PUBLIC_VALIDATION.md)。
