"""Small controlled fixtures, with known defects and actual JPEG payloads."""
import argparse
import io
import json
from pathlib import Path

import h5py
import numpy as np
from PIL import Image


def make_demo(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    truth = {}
    for case in ("normal", "return_to_start", "nan_state", "short", "speed_spike", "duplicate_time", "stationary_review"):
        path = directory / f"{case}.hdf5"
        n = 10 if case == "short" else 60
        time = np.arange(n)/50
        q = np.column_stack([time*.2, time*.1])
        if case == "return_to_start":
            q = np.column_stack([.2*np.sin(np.linspace(0, 2*np.pi, n)), np.zeros(n)])
        if case == "nan_state":
            q[n//2, 0] = np.nan
        if case == "speed_spike":
            q[n//2, 0] += 5
        if case == "stationary_review":
            q[:] = 0
        with h5py.File(path, "w") as handle:
            handle.create_dataset("observations/qpos", data=q)
            handle.create_dataset("action", data=np.column_stack([time*.2, time*.1, time >= .5]))
            handle.create_dataset("timestamps/state", data=time)
            handle.create_dataset("timestamps/action", data=time)
            for camera, fps, offset in [("cam_high", 30, .005), ("cam_wrist", 50, 0)]:
                ct = np.arange(max(2, int(n/50*fps))) / fps+offset
                stream = io.BytesIO()
                Image.new("RGB", (64, 48), (210, 30, 10)).save(stream, "JPEG")
                payload = np.frombuffer(stream.getvalue(), np.uint8)
                handle.create_dataset(f"observations/images/{camera}", data=np.tile(payload, (len(ct), 1)))
                handle.create_dataset(f"timestamps/images/{camera}", data=ct)
            handle.create_dataset("language_instruction", data="Controlled synthetic example", dtype=h5py.string_dtype())
            if case == "duplicate_time":
                handle["timestamps/state"][10] = handle["timestamps/state"][9]
        truth[path.name] = "accepted" if case in ("normal", "return_to_start") else "review" if case == "stationary_review" else "rejected"
    (directory / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    print(f"Generated {len(truth)} tiny synthetic files in {directory}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    make_demo(parser.parse_args().output)
