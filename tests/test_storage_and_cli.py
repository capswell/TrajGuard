import json
from pathlib import Path
import subprocess
import sys

import h5py
import numpy as np
import pytest

from conftest import make_episode
from trajguard.config import Config
from trajguard.pipeline import run


@pytest.mark.parametrize("mode", ["raw", "vlen"])
def test_raw_and_variable_length_images(tmp_path, mode):
    file = tmp_path / "input.h5"
    with h5py.File(file, "w") as source:
        make_episode(source)
        ds = source["observations/images/cam_high"]
        payload = ds[0]
        del source["observations/images/cam_high"]
        if mode == "vlen":
            ds = source.create_dataset("observations/images/cam_high", shape=(30,), dtype=h5py.vlen_dtype(np.dtype("uint8")))
            for index in range(30):
                ds[index] = payload[:len(payload)-index]
        else:
            source.create_dataset("observations/images/cam_high", data=np.full((30, 24, 32, 3), 17, dtype=np.uint8))
    m = run(file, tmp_path / "out", Config())
    job = next(iter(m["jobs"].values()))
    assert job["status"] == "accepted"
    with h5py.File(file, "r") as raw, h5py.File(job["artifact"], "r") as clean:
        for index in range(30):
            np.testing.assert_array_equal(raw["observations/images/cam_high"][index], clean["images/cam_high"][index])


def test_no_partial_hdf5_published_after_write_error(episode_file, tmp_path, monkeypatch):
    import trajguard.storage as storage
    def broken(*args):
        raise OSError("simulated disk-full")
    monkeypatch.setattr(storage, "copy_images", broken)
    result = run(episode_file, tmp_path / "out", Config())
    assert next(iter(result["jobs"].values()))["status"] == "failed"
    assert not list((tmp_path / "out/episodes").glob("*"))


def test_cli_failure_codes_and_json_summary(episode_file, tmp_path):
    repo = Path(__file__).resolve().parents[1]
    valid = subprocess.run([sys.executable, "-m", "trajguard", "run", "--input", str(episode_file), "--output", str(tmp_path / "out")], cwd=repo, capture_output=True, text=True)
    assert valid.returncode == 0
    assert json.loads(valid.stdout)["counts"] == {"accepted": 1}
    invalid = subprocess.run([sys.executable, "-m", "trajguard", "run", "--input", str(tmp_path / "missing"), "--output", str(tmp_path / "bad")], cwd=repo, capture_output=True, text=True)
    assert invalid.returncode == 2
    assert "does not exist" in invalid.stderr


def test_malformed_hdf5_cli_returns_failure(tmp_path):
    file = tmp_path / "bad.h5"
    file.write_bytes(b"broken")
    result = subprocess.run([sys.executable, "-m", "trajguard", "run", "--input", str(file), "--output", str(tmp_path / "out")], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 1


def test_raw_timestamp_scale_applied_before_validation(episode_file, tmp_path):
    with h5py.File(episode_file, "r+") as handle:
        for field in ("timestamps/state", "timestamps/action", "timestamps/images/cam_high"):
            handle[field][:] *= 1000
    m = run(episode_file, tmp_path / "out", Config(timestamp_scale=.001))
    job = next(iter(m["jobs"].values()))
    assert job["status"] == "accepted"
    with h5py.File(job["artifact"], "r") as out:
        assert out["timestamps"][-1] == pytest.approx(29/30)
