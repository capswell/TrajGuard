"""Small explicit HDF5 adapters. Images remain datasets, never eagerly decoded."""
from dataclasses import dataclass
import h5py
import numpy as np


class InvalidEpisode(ValueError):
    pass


@dataclass
class Episode:
    state: np.ndarray
    actions: np.ndarray
    cameras: dict
    state_kind: str
    instruction: str
    state_time: np.ndarray | None
    action_time: np.ndarray | None
    camera_times: dict
    time_sources: dict


def episodes(handle):
    if "data" in handle and isinstance(handle["data"], h5py.Group):
        return [f"data/{key}" for key in sorted(handle["data"]) if isinstance(handle[f"data/{key}"], h5py.Group)]
    return ["/"]


def dataset(group, candidates):
    for key in candidates:
        if key in group and isinstance(group[key], h5py.Dataset):
            return group[key]
    raise InvalidEpisode(f"Missing field; expected one of {candidates}")


def matrix(value, name):
    array = np.asarray(value[:], dtype=np.float64)
    if array.ndim != 2 or not array.shape[1] or len(array) < 2:
        raise InvalidEpisode(f"{name}: expected >=2 frames of a nonempty 2D matrix")
    if not np.isfinite(array).all():
        raise InvalidEpisode(f"{name}: NaN/Inf")
    return array


def timestamps(group, explicit, candidates, count, fps, scale, name):
    value = None
    origin = None
    if explicit:
        if explicit not in group or not isinstance(group[explicit], h5py.Dataset):
            raise InvalidEpisode(f"{name}: configured timestamp field absent: {explicit}")
        value, origin = group[explicit][:], f"recorded:{explicit}"
    else:
        for path in candidates:
            if path in group and isinstance(group[path], h5py.Dataset):
                value, origin = group[path][:], f"recorded:{path}"
                break
    if value is None and fps is not None:
        return np.arange(count, dtype=float) / fps, f"assumed_fps:{fps}"
    if value is None:
        return None, "unavailable"
    value = np.asarray(value, dtype=float)
    if value.shape != (count,) or not np.isfinite(value).all():
        raise InvalidEpisode(f"{name}: timestamps must be finite, 1D and match frame count")
    value = value * scale
    if len(value) < 2 or np.any(np.diff(value) <= 0):
        raise InvalidEpisode(f"{name}: timestamps must be strictly increasing (no duplicates)")
    return value, origin


def read_episode(group, config):
    state_ds = dataset(group, ["observations/qpos", "obs/joint_positions", "obs/robot0_joint_pos", "obs/robot0_eef_pos"])
    state_kind = "eef_position" if state_ds.name.endswith("robot0_eef_pos") else "joint_positions"
    state = matrix(state_ds, "state")
    actions = matrix(dataset(group, ["action", "actions"]), "actions")
    cameras = {}
    if "observations/images" in group:
        cameras = {key: item for key, item in group["observations/images"].items() if isinstance(item, h5py.Dataset)}
    elif "obs/agentview_image" in group:
        cameras = {"agentview": group["obs/agentview_image"]}
    elif "observations/images0" in group:
        cameras = {"images0": group["observations/images0"]}
    if not cameras:
        raise InvalidEpisode("No supported camera datasets")
    if set(config.camera_color_orders) - set(cameras):
        raise InvalidEpisode('Configured color camera names not present')
    for name, values in [('state', state), ('action', actions)]:
        dimensions = getattr(config, f'{name}_semantics').get('dimensions', [])
        if dimensions and len(dimensions) != values.shape[1]:
            raise InvalidEpisode(f'{name} semantic dimensions do not match data')
    if set(config.camera_timestamp_paths) - set(cameras):
        raise InvalidEpisode("Configured timestamp camera names not present in input")
    for name, images in cameras.items():
        raw = images.ndim == 4 and images.shape[-1] == 3 and images.dtype == np.uint8
        encoded = images.dtype == np.uint8 and images.ndim == 2 and images.shape[1] > 0
        vlen = images.ndim == 1 and h5py.check_dtype(vlen=images.dtype) == np.dtype("uint8")
        if len(images) < 2 or not (raw or encoded or vlen):
            raise InvalidEpisode(f"{name}: expected RGB/BGR uint8 frames or encoded uint8 payloads")
    st, ss = timestamps(group, config.state_timestamp_path, ["timestamps/state", "observations/timestamps"], len(state), config.state_fps, config.timestamp_scale, "state")
    at, ass = timestamps(group, config.action_timestamp_path, ["timestamps/action"], len(actions), config.action_fps, config.timestamp_scale, "actions")
    camera_times, sources = {}, {"state": ss, "action": ass}
    for name, images in cameras.items():
        ct, cs = timestamps(group, config.camera_timestamp_paths.get(name), [f"timestamps/images/{name}"], len(images), config.camera_fps, config.timestamp_scale, name)
        camera_times[name], sources[f"camera:{name}"] = ct, cs
    instruction = ""
    if "language_instruction" in group:
        raw = group["language_instruction"][()]
        instruction = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    elif "instruction" in group:
        raw = group["instruction"][()]
        instruction = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    return Episode(state, actions, cameras, state_kind, instruction, st, at, camera_times, sources)
