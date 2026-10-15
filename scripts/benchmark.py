"""Small reproducible JPEG-storage experiment; never presented as 50GB evidence."""
import argparse
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

import h5py
import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from trajguard.resources import peak_rss_bytes


def eager_probe(source):
    started = time.perf_counter()
    with h5py.File(source, "r") as handle:
        frames = handle["observations/images/cam_high"][:]
        expanded = np.stack([np.asarray(Image.open(io.BytesIO(row.tobytes())).convert("RGB")) for row in frames])
        result = {"expanded_pixel_bytes": expanded.nbytes, "frames": len(expanded), "peak_process_rss_bytes": peak_rss_bytes(), "wall_seconds": time.perf_counter()-started}
    print(json.dumps(result))


def benchmark(directory, episodes, frames):
    directory = Path(directory).resolve()
    inputs = directory / "input"
    inputs.mkdir(parents=True, exist_ok=True)
    # Fixed settings and actual JPEGs, not zero-filled images misrepresented as raw sensor data.
    image = Image.new("RGB", (320, 240), (210, 30, 10))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90)
    payload = np.frombuffer(buffer.getvalue(), np.uint8)
    for index in range(episodes):
        with h5py.File(inputs / f"episode_{index}.h5", "w") as handle:
            q = np.arange(frames, dtype=float)[:, None]*.001
            handle.create_dataset("observations/qpos", data=q)
            handle.create_dataset("action", data=q)
            handle.create_dataset("observations/images/cam_high", data=np.tile(payload, (frames, 1)))
    result = {"scope": "synthetic solid-color JPEGs; warm filesystem cache and small data; no production speedup claim", "platform": platform.platform(), "python": sys.version, "episodes": episodes, "frames_per_episode": frames,
              "input_bytes": sum(p.stat().st_size for p in inputs.glob("*.h5")), "runs": []}
    probe = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--eager-probe", str(inputs / "episode_0.h5")], capture_output=True, text=True, check=True)
    result["eager_decode_reference_one_episode"] = json.loads(probe.stdout)
    for workers in (1, 2, 4):
        output = directory / f"workers-{workers}"
        process = subprocess.run([sys.executable, "-m", "trajguard", "run", "--input", str(inputs), "--output", str(output), "--workers", str(workers)], cwd=REPO, capture_output=True, text=True, check=True)
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        assert len(manifest["jobs"]) == episodes
        assert all(j["status"] == "accepted" for j in manifest["jobs"].values())
        rows = list(manifest["jobs"].values())
        result["runs"].append({"workers": workers, "wall_seconds": manifest["wall_seconds"], "frames_per_second": manifest["accepted_frames"] / manifest["wall_seconds"],
                               "output_hdf5_bytes": sum(j["output_bytes"] for j in rows), "max_worker_lifetime_peak_rss_bytes": max((j["worker_peak_rss_bytes"] or 0 for j in rows), default=0)})
    result["measurement_notes"] = ["Wall time covers discovery SHA256, checks, export, output hashing; report rendering occurs after timer.", "RSS is a single worker lifetime peak, not total pool memory.", "Eager probe decodes a single episode but does not run quality checks or write HDF5; not an apples-to-apples throughput comparison.", "Solid-color JPEGs strongly favor lossless compression; natural scenes may compress much less."]
    (directory / "benchmark.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--episodes", type=int, default=4)
    parser.add_argument("--frames", type=int, default=240)
    parser.add_argument("--eager-probe")
    args = parser.parse_args()
    if args.eager_probe:
        eager_probe(args.eager_probe)
    elif args.output and args.episodes > 0 and args.frames >= 15:
        benchmark(args.output, args.episodes, args.frames)
    else:
        parser.error("Specify --output, positive --episodes, and --frames >=15")
