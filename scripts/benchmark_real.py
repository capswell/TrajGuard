"""Repeat real-data runs without duplicating bulk artifacts; independently audit bytes."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

import h5py
import numpy as np

REPO = Path(__file__).resolve().parents[1]


def monitored_run(command):
    try:
        import psutil
    except ImportError:
        psutil = None
    start = time.perf_counter()
    process = subprocess.Popen(command, cwd=REPO, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    peak = 0
    try:
        while process.poll() is None:
            if time.perf_counter()-start > 600:
                raise TimeoutError("Benchmark subprocess exceeded 600 seconds")
            if psutil is not None:
                try:
                    parent = psutil.Process(process.pid)
                    total = 0
                    for child in [parent, *parent.children(recursive=True)]:
                        try:
                            total += child.memory_info().rss
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    peak = max(peak, total)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            time.sleep(.02)
        stdout, stderr = process.communicate()
    except BaseException:
        process.kill()
        process.communicate()
        raise
    elapsed = time.perf_counter()-start
    if process.returncode:
        raise RuntimeError(f"CLI failed ({process.returncode}): {stdout}\n{stderr}")
    return {"external_wall_seconds": elapsed, "sampled_peak_tree_rss_bytes": peak if psutil else None, "stdout": stdout, "stderr": stderr}


def inspect_sources(directory):
    sources = []
    for path in sorted(directory.glob("*.hdf5")):
        with h5py.File(path, "r") as handle:
            datasets = {}
            handle.visititems(lambda name, item: datasets.update({name: {"shape": list(item.shape), "dtype": str(item.dtype)}}) if isinstance(item, h5py.Dataset) else None)
            sources.append({"path": str(path), "bytes": path.stat().st_size, "datasets": datasets,
                            "attributes": {key: value.item() if isinstance(value, np.generic) else str(value) for key, value in handle.attrs.items()}})
    if not sources:
        raise ValueError("No *.hdf5 files found")
    return sources


def audit(manifest):
    results = []
    for job in manifest["jobs"].values():
        if job["status"] != "accepted":
            raise AssertionError(f"No accepted output for {job['source']}: {job['findings']}")
        with h5py.File(job["source"], "r") as source, h5py.File(job["artifact"], "r") as target:
            group = source[job["episode"]]
            np.testing.assert_array_equal(group["observations/qpos"][:], target["state"][:])
            np.testing.assert_array_equal(group["action"][:], target["actions"][:])
            assert job["alignment"]["mode"] == "index_only", "This audit expects unchanged index-only ALOHA exports"
            assert "timestamps" not in target
            cameras = []
            for name, data in group["observations/images"].items():
                exported = target[f"images/{name}"]
                assert data.shape == exported.shape and data.dtype == exported.dtype
                raw_hash, out_hash = hashlib.sha256(), hashlib.sha256()
                for start in range(0, len(data), 32):
                    raw_block, out_block = data[start:start+32], exported[start:start+32]
                    np.testing.assert_array_equal(raw_block, out_block)
                    raw_hash.update(raw_block.tobytes())
                    out_hash.update(out_block.tobytes())
                np.testing.assert_array_equal(target[f"source_indices/images/{name}"][:], np.arange(len(data)))
                assert raw_hash.hexdigest() == out_hash.hexdigest()
                cameras.append({"name": name, "frames": len(data), "shape": list(data.shape), "payload_sha256": raw_hash.hexdigest(), "all_payload_bytes_equal": True})
            results.append({"source": job["source"], "artifact": job["artifact"], "source_sha256": json.loads(target.attrs["provenance"])["source_sha256"], "state_frames": len(target["state"]), "state_dimensions": target["state"].shape[1], "action_dimensions": target["actions"].shape[1], "state_and_action_values_equal": True, "cameras": cameras, "output_bytes": Path(job["artifact"]).stat().st_size, "alignment_mode": "index_only"})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--config", default=str(REPO / "configs/aloha_blog.json"))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--workers", type=int, nargs="+", default=[1, 2])
    args = parser.parse_args()
    if args.repeats < 1 or any(w < 1 for w in args.workers):
        parser.error("Positive repeats/workers required")
    inputs, output = Path(args.input).resolve(), Path(args.output).resolve()
    if inputs == output or inputs in output.parents:
        parser.error("Output must be outside input")
    output.mkdir(parents=True, exist_ok=True)
    sources = inspect_sources(inputs)
    config_path = Path(args.config).resolve()
    command = [sys.executable, "-m", "trajguard", "run", "--input", str(inputs), "--output", str(output / "processed"), "--config", str(config_path)]
    result = {"scope": "real ALOHA episodes from the blog; stable inputs; warm filesystem cache, no cache flush", "platform": platform.platform(), "python": sys.version, "tool_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(), "config": json.loads(config_path.read_text(encoding="utf-8")), "sources": sources, "trials": []}
    for repeat in range(args.repeats):
        for workers in args.workers:
            metrics = monitored_run(command + ["--workers", str(workers)])
            manifest = json.loads((output / "processed/manifest.json").read_text(encoding="utf-8"))
            if any(j["status"] != "accepted" for j in manifest["jobs"].values()):
                raise AssertionError("Real sample rejected; inspect processed/manifest.json before benchmarking")
            metrics.update(repeat=repeat+1, workers=workers, pipeline_wall_seconds=manifest["wall_seconds"], accepted_frames=manifest["accepted_frames"], counts=dict(Counter(j["status"] for j in manifest["jobs"].values())), output_bytes=sum(j.get("output_bytes", 0) for j in manifest["jobs"].values()), max_worker_lifetime_peak_rss_bytes=max(j["worker_peak_rss_bytes"] or 0 for j in manifest["jobs"].values()))
            result["trials"].append(metrics)
            print(f"repeat={repeat+1}, workers={workers}, pipeline={metrics['pipeline_wall_seconds']:.3f}s, total={metrics['external_wall_seconds']:.3f}s", flush=True)
            (output / "benchmark.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["summary"] = [{"workers": workers, "median_pipeline_seconds": statistics.median(t["pipeline_wall_seconds"] for t in result["trials"] if t["workers"] == workers), "median_external_seconds": statistics.median(t["external_wall_seconds"] for t in result["trials"] if t["workers"] == workers), "max_worker_peak_rss_bytes": max(t["max_worker_lifetime_peak_rss_bytes"] for t in result["trials"] if t["workers"] == workers), "max_sampled_tree_rss_bytes": max((t["sampled_peak_tree_rss_bytes"] or 0) for t in result["trials"] if t["workers"] == workers)} for workers in args.workers]
    # Audit every selected byte, not only frame counts or a first/last thumbnail.
    final_manifest = json.loads((output / "processed/manifest.json").read_text(encoding="utf-8"))
    result["audit"] = audit(final_manifest)
    resumed = monitored_run(command + ["--workers", str(args.workers[-1]), "--resume"])
    resumed_manifest = json.loads((output / "processed/manifest.json").read_text(encoding="utf-8"))
    assert resumed_manifest["processed"] == 0 and resumed_manifest["resumed"] == len(final_manifest["jobs"])
    resumed.update(pipeline_wall_seconds=resumed_manifest["wall_seconds"], processed=resumed_manifest["processed"], resumed=resumed_manifest["resumed"])
    result["resume"] = resumed
    result["notes"] = ["Pipeline timing includes source hashing, checks, export and output hashing; excludes final report rendering and independent byte audit.", "External timing includes Python/process startup and report writing; downloads excluded.", "Tree RSS sampled every 20ms sums RSS including shared pages and may miss short peaks; worker lifetime peak is a different metric.", "No timestamps in these samples: index_only is not evidence for physical time alignment accuracy or velocity thresholds.", "Acceptance on two demonstration files is not an anomaly-detection precision/recall estimate.", "Only supported state/actions/cameras are exported; base_action/effort/qvel and other unsupported source fields remain in original files.", "Repeated runs replace the same signed artifact paths, keeping only one bulk processed copy."]
    (output / "benchmark.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": result["summary"], "resume": resumed, "audited_episodes": len(result["audit"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
