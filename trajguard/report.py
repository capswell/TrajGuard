"""Dependency-free HTML report; dataset membership is defined by the manifest."""
from collections import Counter
from html import escape
import os
from pathlib import Path
from urllib.parse import quote


def render_report(manifest, path):
    counts = Counter(item["status"] for item in manifest["jobs"].values())
    rows = []
    for item in manifest["jobs"].values():
        status = item["status"]
        findings = "; ".join(f"{f['rule']}: {f['message']}" for f in item.get("findings", []))
        artifact = item.get("artifact")
        link = ""
        if artifact:
            relative = os.path.relpath(artifact, Path(path).parent).replace(os.sep, "/")
            link = f'<a href="{escape(quote(relative), quote=True)}">HDF5</a>'
        metrics = item.get("metrics", {})
        rows.append(f'<tr data-status="{escape(status)}"><td>{escape(item["source"])}</td><td>{escape(item["episode"])}</td><td>{status}</td><td>{escape(str(item.get("alignment", {}).get("mode", "—")))}</td><td>{metrics.get("state_frames", "—")}</td><td>{escape(findings)}</td><td>{link}</td></tr>')
    summary = " · ".join(f"{status}: {counts[status]}" for status in ("accepted", "review", "rejected", "failed"))
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>TrajGuard 质检报告</title>
<style>body{font:15px system-ui;max-width:1400px;margin:36px auto;padding:0 24px;color:#203047;background:#f5f7fb}h1{color:#173d68}table{border-collapse:collapse;background:white;width:100%}td,th{padding:12px;border-bottom:1px solid #dce2eb;text-align:left;overflow-wrap:anywhere}th{background:#e5edf8}p{line-height:1.7}select{padding:8px;margin:12px 0}tr[data-status=failed],tr[data-status=rejected]{background:#fff3f2}tr[data-status=review]{background:#fffbea}</style>
<h1>TrajGuard · 轨迹数据质检</h1><p>SUMMARY</p>
<p>accepted 仅代表通过已配置规则，不代表任务成功。review 进入人工审核；encoded_payload_unvalidated 表示保留编码字节，尚未解码检查图像质量。消费数据集请以 manifest.json 中 accepted 的 artifact 列表为准。</p>
<p>时间模式：recorded_timestamps = 记录的时间戳；assumed_rate = 包含显式采样率假设；index_only = 无时间信息，仅按帧索引配对。状态阈值以配置声明的单位为准。</p>
<label>筛选状态 <select id="status"><option value="all">全部</option><option>accepted</option><option>review</option><option>rejected</option><option>failed</option></select></label>
<table><thead><tr><th>来源文件</th><th>Episode</th><th>结果</th><th>时间模式</th><th>状态帧数</th><th>问题与建议</th><th>成品</th></tr></thead><tbody>ROWS</tbody></table>
<script>document.getElementById('status').onchange=function(){document.querySelectorAll('tbody tr').forEach(r=>r.hidden=this.value!=='all'&&r.dataset.status!==this.value)}</script></html>'''
    Path(path).write_text(page.replace("SUMMARY", escape(summary)).replace("ROWS", "\n".join(rows)), encoding="utf-8")
