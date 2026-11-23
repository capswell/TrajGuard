# 扩展数据源与导出格式

以现有 ALOHA 适配器为例：adapters.episodes(handle) 枚举根组或 data/demo_*；read_episode(group, config) 返回 Episode。state/actions 是有限二维数组，cameras 是延迟读取的 h5py.Dataset；各流时间数组及 time_sources 单独记录。HDF5 句柄在 process_job 的 with 块中存活，不能提前关闭或返回悬空数据集。

新增来源先识别准确的布局，再映射到 Episode：不得根据 7/14 维推断控制含义。缺失必需字段抛 InvalidEpisode，消息写清路径；真正 I/O 故障由 pipeline 记录 failed。将输入原始属性放在 episode 组，pipeline 会以 source_metadata 字符串值保留。source_identity 可记录稳定来源标识；DROID 转换器展示独立预转换入口，适合依赖较重的 TFDS 来源。身份对象的序列化需稳定，避免将临时路径作为唯一来源。

Config.state_semantics/action_semantics 保存 representation、unit、coordinate_frame、rotation、gripper、time_interval、frequency 和 dimensions（name/unit 列表）；缺省为空，语义未知。camera_color_orders 逐相机声明 rgb/bgr/unknown。现有 state_unit 仍决定速度检查单位；这些语义声明不是自动坐标转换。显式姿态线性重采样会被拒绝，需要另行实现经测试的 SO(3)/SE(3) 插值。

时间处理交给 alignment；不要为迎合等长数组伪造记录时间。缺少时间可以使用明确频率假设或 index_only。输出保留模式、过滤数量、来源索引与源时间。

新增导出器可参考 lerobot_export.export(manifest_path, output, config_path, resume=False)：

1. 只读取当前 accepted 成品，检查哈希与目标所需语义。
2. 显式映射字段、相机和任务，按需解码，验证颜色与尺寸。
3. 按目标时间要求检查或切片，记录源/成品/目标帧映射。
4. 使用目标公开 API；可选依赖延迟导入；CLI 未安装时给出安装提示。
5. 临时目标完成并通过真实读取后再发布；恢复校验完整成品，不把文件存在当成功。

必要测试：字段优先级、多 episode、多相机、缺失字段、非法数值、坏图像、颜色、不同维度、时间缺口和边界、离散动作、失败目录、重复执行、来源传播与真实目标读取。合成 fixture 必须标注用途；真实数据测试注明发行形式及获准使用的来源，不提交私有采集或大数据包。导出集成测试当前由 optional LeRobot 环境运行；基础环境跳过它。