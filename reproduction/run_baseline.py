"""Run upstream scripts in an isolated copy; keep tracked fixtures untouched."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


REPO = Path(__file__).resolve().parents[1]
WORKSPACE = REPO.parent
RUN = WORKSPACE / "work" / "baseline"
OUT = WORKSPACE / "outputs" / "baseline"


def run_step(name, *arguments):
    started = time.perf_counter()
    process = subprocess.run(
        [sys.executable, *arguments], cwd=RUN,
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="replace", timeout=300,
    )
    (OUT / f"{name}.log").write_text(process.stdout, encoding="utf-8")
    print(f"{name}: exit={process.returncode}, {time.perf_counter() - started:.2f}s", flush=True)
    if process.returncode:
        raise RuntimeError(process.stdout)


def verify_clean(source, clean, video):
    import cv2
    import h5py
    import numpy as np

    with h5py.File(source, "r") as raw, h5py.File(clean, "r") as result:
        shapes = {key: list(result[key].shape) for key in ("images", "qpos", "actions")}
        assert shapes["images"][0] == shapes["qpos"][0] == shapes["actions"][0]
        assert np.array_equal(raw["observations/qpos"][:], result["qpos"][:])
        label = result["instruction"][()]
        label = label.decode("utf-8") if isinstance(label, bytes) else str(label)
        assert label
    capture = cv2.VideoCapture(str(video))
    count = 0
    while True:
        ok, _ = capture.read()
        if not ok:
            break
        count += 1
    capture.release()
    assert count == shapes["images"][0], (count, shapes)
    return {"shapes": shapes, "mock_instruction": label, "decoded_video_frames": count}


def main():
    import h5py
    import numpy as np

    parser = argparse.ArgumentParser()
    parser.add_argument("--synthetic-only", action="store_true")
    args = parser.parse_args()
    RUN.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for source in REPO.glob("*.py"):
        shutil.copy2(source, RUN / source.name)
    run_step("01_generate", "generate_test_cases.py")
    run_step("02_filter", "kinematic_filter.py")
    run_step("03_sync", "time_sync_show.py")
    run_step("04_mock_relabel", "vlm_relabel.py")
    run_step("05_pipeline", "main_pipeline.py")
    run_step("06_inspect", "inspect_clean_data.py")
    run_step("07_parser_video", "-c", "from bridge_parser import VLADatasetParser; p=VLADatasetParser('test_data/case1_perfect.hdf5'); p.extract_trajectory(); p.export_to_mp4('synthetic.mp4')")

    sys.path.insert(0, str(RUN))
    from kinematic_filter import KinematicFilter
    checks = []
    for path, expected in zip(sorted((RUN / "test_data").glob("*.hdf5")), [True, False, False, False]):
        with h5py.File(path, "r") as data:
            passed, reasons, movement, velocity = KinematicFilter().run_checks(data["observations/qpos"][:], data["action"][:])
        assert passed == expected, (path.name, passed)
        checks.append({"file": path.name, "passed": passed, "reasons": reasons, "net_movement": float(movement), "max_frame_difference": float(velocity)})
    assert sorted(p.name for p in (RUN / "clean_data").glob("*.hdf5")) == ["clean_case1_perfect.hdf5"]
    result = {"python": sys.version, "vlm_mode": "mock (random preset text, no model inference)", "synthetic_checks": checks}
    result["synthetic_output"] = verify_clean(RUN / "test_data/case1_perfect.hdf5", RUN / "clean_data/clean_case1_perfect.hdf5", RUN / "synthetic.mp4")
    shutil.copy2(RUN / "clean_data/clean_case1_perfect.hdf5", OUT / "clean_case1_perfect.hdf5")
    shutil.copy2(RUN / "synthetic.mp4", OUT / "synthetic.mp4")

    real = RUN / "real_data/episode_0.hdf5"
    if not args.synthetic_only and real.exists() and h5py.is_hdf5(real):
        structure = []
        with h5py.File(real, "r") as data:
            data.visititems(lambda name, item: structure.append({"key": name, "shape": list(item.shape), "dtype": str(item.dtype)}) if isinstance(item, h5py.Dataset) else None)
        (OUT / "real_structure.json").write_text(json.dumps(structure, indent=2), encoding="utf-8")
        run_step("08_real_parser", "-c", "from bridge_parser import VLADatasetParser; p=VLADatasetParser('real_data/episode_0.hdf5'); p.extract_trajectory(); p.export_to_mp4('real_raw.mp4')")
        run_step("09_real_pipeline", "-c", "from main_pipeline import run_parallel_pipeline; run_parallel_pipeline('real_data','real_clean')")
        real_clean = RUN / "real_clean/clean_episode_0.hdf5"
        if real_clean.exists():
            run_step("10_real_video", "-c", "from bridge_parser import VLADatasetParser; import h5py; p=VLADatasetParser(''); f=h5py.File('real_clean/clean_episode_0.hdf5','r'); p.data_dict['images']=f['images'][:]; f.close(); p.export_to_mp4('real_clean.mp4')")
            result["real_output"] = verify_clean(real, real_clean, RUN / "real_clean.mp4")
            result["real_input_sha256"] = hashlib.sha256(real.read_bytes()).hexdigest()
            for source, destination in [(real_clean, "clean_episode_0.hdf5"), (RUN / "real_raw.mp4", "real_raw.mp4"), (RUN / "real_clean.mp4", "real_clean.mp4")]:
                shutil.copy2(source, OUT / destination)
        else:
            result["real_output"] = "No output: inspect parser and pipeline logs for parsing errors or rule rejection"
    else:
        result["real_output"] = "Skipped or no valid real HDF5 downloaded; not reproduced"
    (OUT / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    frozen = subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True)
    (REPO / "reproduction/requirements-lock.txt").write_text(frozen, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
