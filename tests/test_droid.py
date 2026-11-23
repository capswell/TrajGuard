import h5py
import numpy as np
import pytest
from trajguard.droid import CAMERAS, convert_episode
from trajguard.adapters import read_episode
from trajguard.config import Config


def test_official_schema_fixture(tmp_path):
    rows = []
    for i in range(3):
        obs = {'joint_position': np.arange(7)+i, 'gripper_position': np.array([.5])}
        obs.update({k: np.zeros((12, 16, 3), np.uint8) for k in CAMERAS})
        rows.append({'is_first': i == 0, 'is_last': i == 2, 'language_instruction': b'move',
            'observation': obs, 'action_dict': {'joint_position': np.arange(7)+i+.1, 'gripper_position': [.2]}})
    path = tmp_path / 'droid.hdf5'
    convert_episode(rows, {'file_path': b'fixture'}, path)
    with h5py.File(path) as h:
        ep = read_episode(h, Config())
        assert ep.state.shape == ep.actions.shape == (3, 8)
        assert len(ep.cameras) == 3
        assert ep.state_time is None
        assert ep.actions[0, 0] == .1
    with pytest.raises(ValueError):
        convert_episode(rows, {}, path)
