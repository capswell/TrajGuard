# 许可证、数据和发布状态

本仓库当前没有完整的项目 LICENSE 文件。不要把它解释为已获得整个仓库的 MIT 授权。

保留的根目录脚本 bridge_parser.py、kinematic_filter.py、time_sync.py、time_sync_show.py、vlm_relabel.py、main_pipeline.py、inspect_clean_data.py、generate_test_cases.py，以及上游样例/视频，来自 Escapist-coder/VLA-Data-Pipeline。原始说明保存在 docs/UPSTREAM_README.md。上游 README 曾出现 MIT 徽章，但仓库快照未包含授权文本。分发前需确认实际许可范围和必要版权声明。

trajguard/、新增 scripts/、tests/、configs/ 及社区文档的许可证由维护者决定；本轮没有擅自为第三方内容补发授权。开源发布待办：确认上游许可；选择自有代码许可证并标明排除范围；核查所有二进制样例来源。GitHub 可见不代表可任意再许可。

数据：公开 ALOHA 下载链接及校验值见 docs/assets/aloha-download-receipts.json；尚未核实其独立再分发许可。DROID 按官方发行条件下载使用，当前不随包提供。相机画面可能含人员和实验室信息，公开演示应另行确认使用条件。tests/conftest.py 与 scripts/make_demo.py 运行时生成的合成样本仅用于逻辑验证，不代表真实机器人性能；它们不需要下载公开数据。

本轮未推送、未替换已发布仓库的许可证声明。源码归属与数据使用条件确认不阻碍继续本地实现和测试。