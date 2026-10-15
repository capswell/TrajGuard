import io

import h5py
import numpy as np
import pytest
from PIL import Image


def make_episode(group, n=30, times=True, camera_n=None, stationary=False):
    camera_n = camera_n or n
    q = np.column_stack([np.linspace(0, 1, n), np.sin(np.linspace(0, 2*np.pi, n))])
    if stationary:
        q[:] = 0
    group.create_dataset("observations/qpos", data=q)
    group.create_dataset("action", data=np.column_stack([q, (np.arange(n) >= n//2).astype(float)]))
    stream = io.BytesIO()
    Image.new("RGB", (32, 24), (220, 30, 10)).save(stream, format="JPEG")
    payload = np.frombuffer(stream.getvalue(), dtype=np.uint8)
    group.create_dataset("observations/images/cam_high", data=np.tile(payload, (camera_n, 1)))
    group.create_dataset("language_instruction", data="Move the object", dtype=h5py.string_dtype())
    if times:
        group.create_dataset("timestamps/state", data=np.arange(n)/30)
        group.create_dataset("timestamps/action", data=np.arange(n)/30)
        group.create_dataset("timestamps/images/cam_high", data=np.arange(camera_n)/30)
    return payload


@pytest.fixture
def episode_file(tmp_path):
    path = tmp_path / "input.hdf5"
    with h5py.File(path, "w") as handle:
        make_episode(handle)
    return path
