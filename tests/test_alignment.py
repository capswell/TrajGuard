from dataclasses import replace

import h5py
import numpy as np
import pytest

from trajguard.adapters import InvalidEpisode, read_episode
from trajguard.alignment import align, bracket_valid
from trajguard.config import Config
from conftest import make_episode


def test_equal_counts_with_real_offset_are_not_skipped(episode_file):
    with h5py.File(episode_file, "r+") as handle:
        handle["timestamps/images/cam_high"][:] += .01
        handle["observations/qpos"][:, 0] = handle["timestamps/state"][:]
        item = read_episode(handle, Config())
        result = align(item, Config())
    assert result["metadata"]["mode"] == "recorded_timestamps"
    np.testing.assert_allclose(result["state"][:, 0], result["timestamps"])
    assert len(result["state"]) == 29


def test_discrete_actions_use_past_only(episode_file):
    config = Config(action_interpolation="linear", discrete_action_indices=(2,))
    with h5py.File(episode_file, "r+") as handle:
        handle["timestamps/images/cam_high"][:] += .02
        item = read_episode(handle, config)
        result = align(item, config)
    expected = item.actions[np.searchsorted(item.action_time, result["timestamps"], side="right")-1, 2]
    np.testing.assert_array_equal(result["actions"][:, 2], expected)
    assert set(expected) == {0, 1}


def test_no_time_information_is_labeled_index_only(tmp_path):
    with h5py.File(tmp_path / "x.h5", "w") as handle:
        make_episode(handle, times=False)
        result = align(read_episode(handle, Config()), Config())
    assert result["timestamps"] is None
    assert result["metadata"]["mode"] == "index_only"


def test_explicit_rates_are_labeled_assumptions(tmp_path):
    cfg = Config(state_fps=30, action_fps=30, camera_fps=30)
    with h5py.File(tmp_path / "x.h5", "w") as handle:
        make_episode(handle, times=False)
        assert align(read_episode(handle, cfg), cfg)["metadata"]["mode"] == "assumed_rate"


@pytest.mark.parametrize("mutation", ["duplicate", "reverse", "nan", "shape"])
def test_invalid_timestamps_rejected(episode_file, mutation):
    with h5py.File(episode_file, "r+") as handle:
        ds = handle["timestamps/state"]
        if mutation == "duplicate":
            ds[3] = ds[2]
        elif mutation == "reverse":
            ds[:] = ds[:][::-1]
        elif mutation == "nan":
            ds[4] = np.nan
        else:
            del handle["timestamps/state"]
            handle.create_dataset("timestamps/state", data=np.arange(29))
        with pytest.raises(InvalidEpisode, match="timestamp"):
            read_episode(handle, Config())


def test_partial_timing_rejected(episode_file):
    with h5py.File(episode_file, "r+") as handle:
        del handle["timestamps/action"]
        with pytest.raises(InvalidEpisode, match="Partial"):
            align(read_episode(handle, Config()), Config())


def test_unequal_counts_without_timing_rejected(tmp_path):
    with h5py.File(tmp_path / "x.h5", "w") as handle:
        make_episode(handle, times=False, camera_n=20)
        with pytest.raises(InvalidEpisode, match="Unequal"):
            align(read_episode(handle, Config()), Config())


def test_no_interpolation_across_large_gap_but_exact_sample_is_valid():
    result = bracket_valid(np.array([0., .1, 10., 10.1]), np.array([.05, 5., 10.]), .2)
    np.testing.assert_array_equal(result, [True, False, True])


def test_no_overlap_rejected(episode_file):
    with h5py.File(episode_file, "r+") as handle:
        handle["timestamps/images/cam_high"][:] += 10
        with pytest.raises(InvalidEpisode, match="overlap"):
            align(read_episode(handle, Config()), Config())


def test_multiple_camera_sampling_is_causal(episode_file):
    with h5py.File(episode_file, "r+") as handle:
        payload = handle["observations/images/cam_high"][:]
        handle.create_dataset("observations/images/wrist", data=payload)
        handle.create_dataset("timestamps/images/wrist", data=np.arange(30)/30+.01)
        item = read_episode(handle, Config())
        result = align(item, Config())
        selected = item.camera_times["wrist"][result["camera_indices"]["wrist"]]
    assert np.all(selected <= result["timestamps"])
    assert result["metadata"]["dropped_reference_frames"] > 0
