# 博客基线复现

基线：上游提交 `0707ad7`。原有 Python 脚本不修改，复制到工作目录运行，避免覆盖仓库中已跟踪的测试数据及缓存。

## Windows / PowerShell

在仓库根目录运行（当前环境已创建）：

```powershell
& '..\work\vla-env\python.exe' '.\reproduction\run_baseline.py'
# 真实数据已下载到 work/baseline/real_data 后：
& '..\work\vla-env\python.exe' '.\reproduction\adapt_real.py'
```

新机器先创建 Python 3.10 环境，再安装本目录的 `requirements-lock.txt`：

```powershell
conda create -n vla_pipeline python=3.10 pip -y
conda activate vla_pipeline
python -m pip install -r reproduction/requirements-lock.txt
python reproduction/run_baseline.py
```

工作副本位于仓库同级 `work/baseline`，日志、核验结果、视频和输出 HDF5 位于仓库同级 `outputs/baseline`。

## 顺序与预期

1. `generate_test_cases.py`：生成正常、过短、静止、跳变四种合成轨迹。图像全黑。
2. `kinematic_filter.py`：四条轨迹中只有正常轨迹通过。
3. `time_sync_show.py`：30 帧相机与 50 帧机器人状态重采样，输出 `(30, 8)`。
4. `vlm_relabel.py`：原有 Mock 路径，随机返回预设文本。
5. `main_pipeline.py`：上游多进程入口，4 条输入、1 条输出。
6. `inspect_clean_data.py`：核验 images `(150, 224, 224, 3)`、qpos/actions `(150, 14)`。
7. 调用原解析器导出 MP4，并实际解码检查帧数。
8. 若 `work/baseline/real_data/episode_0.hdf5` 是有效 HDF5，额外运行真实数据解析、过滤、流水线和视频导出。

## 本次真实数据复现结论

博客链接中的真实文件为 140154944 字节，含 2000 帧，图像字段为 `cam_high/cam_left_wrist/cam_right_wrist`，每帧以 JPEG 字节存储。上游解析器直接运行报“未找到标准图像字段”，进程虽返回 0，但没有生成成品，不能判定复现成功。

`adapt_real.py` 为独立的格式兼容步骤：选取 `cam_high`，逐帧 JPEG 解码并按该样本的 RGB 通道约定存储（已与上游视频核对），映射为 `observations/images/top`。保留 2000 帧和 480×640 分辨率，复制 qpos/action；未适配另外两个相机、base_action、effort/qvel。原始文件保留。

随后调用工作副本中的原流水线，1 条输入、1 条通过。输出 images `(2000,480,640,3)`，qpos/actions `(2000,14)`；核验动作与关节数组一致，首/中/末帧与原始 JPEG 解码结果逐像素一致，视频实际解码 2000 帧。视频明确叠加 MOCK 标记，使用假定 30fps 预览，未验证真实时间戳对齐。

产物位于 `outputs/baseline/adapted_real`，视频约 66.7 秒，完整核验见 `verification.json`。

## 实验边界

- 不调用真实 VLM、不需要 API Key；随机文本不是根据画面生成的可靠标注。
- 原脚本帧数相等时跳过同步，合成流水线与真实流水线并不能单独验证不同频率对齐；独立的 `time_sync_show.py` 才演示了重采样。
- 输出通过只代表满足上游三项规则，不能证明机器人任务成功。
- 小样本耗时不代表 50GB 性能，未复现 README 的加速比。
- 上游 README 的 `--input` / `--output` 没有参数解析；本复现直接调用函数指定真实数据目录。
- 随机 Mock 导致多次运行的标签可能不同。

真实数据来自博客所链接的公开 Google Drive 文件夹：
https://drive.google.com/drive/folders/1vhKa4tNPfMkeK7SW86vKorb39epTYW39

博客： https://blog.csdn.net/2303_77547168/article/details/158650625

颜色约定：本样本的 OpenCV JPEG 解码结果已按 RGB 含义排列，不能再按普通 BGR JPEG 额外交换一次通道。已对照 assets/demo.mp4 的 cam_high 面板，在首/中/末帧验证修正后视频的颜色误差低于修正前。该约定只适用于此样本，不能推广到所有 JPEG 数据。
