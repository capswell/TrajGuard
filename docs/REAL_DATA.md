# 真实 ALOHA 数据实验

## 来源与准备

使用项目博客链接的 [公开 Google Drive 数据目录](https://drive.google.com/drive/folders/1vhKa4tNPfMkeK7SW86vKorb39epTYW39)，选取：

| 文件 | Google Drive ID | 目录标注字节数 |
|---|---|---:|
| episode_0.hdf5 | 11M3Ye0r5agMaaicPbVGD0q2Hb3rGklbb | 140154944 |
| episode_1.hdf5 | 1-tx7SvYYgSvXCvnf_EI2OVdwK-CkFY6S | 143802944 |

下载到仓库同级 `data/aloha-blog/`。目录应只有这两条实验轨迹与可选下载凭据，不要混入其他 HDF5。原文件保留不修改；成品仍保存编码图像，不提前解码或转换颜色。

## 复现命令

```bash
python -m pip install -e ".[benchmark]"
python scripts/benchmark_real.py --input ../data/aloha-blog --output ../outputs/aloha-real --config configs/aloha_blog.json --repeats 3 --workers 1 2
```

桌面目录的 Windows PowerShell 可用 `& 'D:\anaconda\python.exe'` 代替 python。

## 测量口径

- 交替执行 1/2 worker，各重复 3 次；不人为清理操作系统缓存，报告中位数和每次原始记录。
- pipeline_wall_seconds 含输入 SHA256、质检、复制编码帧、成品哈希；不含末尾 HTML 报告和独立字节审核。
- external_wall_seconds 还包括 Python/工作进程启动和报告写入；不包括下载。
- worker_peak_rss 是单个工作进程生命周期峰值；另以 20ms 周期采样进程树 RSS 之和，包含共享页重复计算且可能漏掉短峰值，不是严格的独占内存。
- 所有重复实验复用同一份签名成品，不为每轮复制大文件。
- 逐块核验每路相机的全部编码字节、源帧索引以及状态/动作数值；不只看文件存在或帧数。
- 最后重跑 resume，要求 processed=0、resumed=2。恢复仍然读取源/成品计算哈希。

结果在 `benchmark.json`；最终可筛选质检报告位于 `processed/report.html`，成品清单位于 `processed/manifest.json`。

## 不能从本实验推导的结论

没有记录时间戳时使用 index_only，不假设 30/50Hz，也不把它当成物理同步精度证据。配置不设未经验证的机械臂速度阈值。两条示范轨迹通过基础质检不等于检测准确率 100%。未执行真实 VLM 或策略训练，不报告标注准确率、机器人成功率。base_action/effort/qvel 等未支持字段仅保留在原文件，输出范围以 TrajGuard schema 为准。
