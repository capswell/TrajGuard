"""Explicit single-camera format adapter for the blog's compressed ALOHA sample."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import cv2
import h5py
import numpy as np

from run_baseline import OUT, RUN, verify_clean


def main():
    source = RUN / "real_data/episode_0.hdf5"
    normalized = RUN / "normalized_real/episode_0.hdf5"
    normalized.parent.mkdir(parents=True, exist_ok=True)
    destination = OUT / "adapted_real"
    destination.mkdir(parents=True, exist_ok=True)
    with h5py.File(source, "r") as raw, h5py.File(normalized, "w") as target:
        images = raw["observations/images/cam_high"]
        first = cv2.imdecode(images[0], cv2.IMREAD_COLOR)
        if first is None:
            raise ValueError("Cannot decode first frame")
        shape = (len(images), *first.shape)
        decoded = target.create_dataset("observations/images/top", shape=shape, dtype="uint8", chunks=(1, *first.shape), compression="lzf")
        for index in range(len(images)):
            frame = cv2.imdecode(images[index], cv2.IMREAD_COLOR)
            if frame is None or frame.shape != first.shape:
                raise ValueError(f"Invalid frame {index}")
            # This sample was JPEG-encoded from RGB arrays using OpenCV.
            # Its imdecode result already has RGB channel semantics, as checked
            # against the corresponding cam_high panel in assets/demo.mp4.
            decoded[index] = frame
        target.create_dataset("observations/qpos", data=raw["observations/qpos"][:])
        target.create_dataset("action", data=raw["action"][:])
        target.attrs["source_camera"] = "cam_high"
        target.attrs["adapter"] = "JPEG decode with sample-specific RGB channel order verified against upstream video; no resize or temporal sampling"
        target.attrs["source_file"] = source.name
    print(f"Decoded {shape[0]} frames at {shape[1:]} without resizing", flush=True)
    command = "from main_pipeline import run_parallel_pipeline; run_parallel_pipeline('normalized_real', " + repr(str(destination)) + ")"
    process = subprocess.run([sys.executable, "-c", command], cwd=RUN, env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8", timeout=300)
    (destination / "pipeline.log").write_text(process.stdout, encoding="utf-8")
    if process.returncode:
        raise RuntimeError(process.stdout)
    clean = destination / "clean_episode_0.hdf5"
    video = destination / "real_mock_preview.mp4"
    with h5py.File(clean, "r") as data:
        images = data["images"]
        label = data["instruction"][()].decode("utf-8")
        height, width = images.shape[1:3]
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 30, (width, height))
        if not writer.isOpened():
            raise RuntimeError("Video writer failed")
        for index in range(len(images)):
            frame = cv2.cvtColor(images[index], cv2.COLOR_RGB2BGR)
            cv2.rectangle(frame, (0, 0), (width, 35), (0, 0, 0), -1)
            cv2.putText(frame, "Real ALOHA / MOCK labels / 30fps preview", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 255, 255), 1)
            cv2.rectangle(frame, (0, height-65), (width, height), (0, 0, 0), -1)
            for line, text in enumerate([label[:75], label[75:150]]):
                cv2.putText(frame, text, (10, height-42+line*22), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 255, 255), 1)
            writer.write(frame)
        writer.release()
    result = verify_clean(normalized, clean, video)
    with h5py.File(source, "r") as raw, h5py.File(clean, "r") as processed:
        assert np.array_equal(raw["action"][:], processed["actions"][:])
        for index in [0, shape[0]//2, shape[0]-1]:
            expected = cv2.imdecode(raw["observations/images/cam_high"][index], cv2.IMREAD_COLOR)
            assert np.array_equal(expected, processed["images"][index])
    reference = cv2.VideoCapture(str(Path(__file__).resolve().parents[1] / "assets/demo.mp4"))
    exported = cv2.VideoCapture(str(video))
    color_checks = []
    with h5py.File(source, "r") as raw:
        for index in [0, shape[0]//2, shape[0]-1]:
            reference.set(cv2.CAP_PROP_POS_FRAMES, index)
            exported.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok_ref, reference_frame = reference.read()
            ok_out, exported_frame = exported.read()
            assert ok_ref and ok_out
            reference_frame = reference_frame[35:height-65, :width].astype(float)
            decoded = cv2.imdecode(raw["observations/images/cam_high"][index], cv2.IMREAD_COLOR)[35:height-65].astype(float)
            prior_error = float(np.abs(decoded-reference_frame).mean())
            corrected_error = float(np.abs(exported_frame[35:height-65].astype(float)-reference_frame).mean())
            assert corrected_error < prior_error, (index, prior_error, corrected_error)
            color_checks.append({"frame": index, "previous_mae": prior_error, "corrected_mae": corrected_error})
    reference.release()
    exported.release()
    result.update({"source_bytes": source.stat().st_size, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "source_camera": "cam_high", "adapter": "all frames JPEG decoded; sample-specific RGB order verified against upstream video; no resizing; other cameras omitted", "color_checks_vs_upstream_video": color_checks, "fps": "30fps preview assumption; no real timestamp synchronization verified", "label_mode": "random upstream mock; unrelated to video contents"})
    (destination / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
