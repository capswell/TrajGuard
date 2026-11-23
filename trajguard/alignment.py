"""Bounded resampling over overlap only. Discrete commands use causal holds."""
import numpy as np

from .adapters import InvalidEpisode


def previous_indices(times, target):
    return np.searchsorted(times, target, side="right") - 1


def bracket_valid(times, target, max_gap):
    right = np.searchsorted(times, target, side="left")
    right = np.clip(right, 0, len(times)-1)
    exact = times[right] == target
    left = np.clip(right - 1, 0, len(times)-1)
    return exact | ((target >= times[0]) & (target <= times[-1]) & ((times[right]-times[left]) <= max_gap))


def resample(times, values, target, mode="linear", discrete=()):
    if mode == "previous":
        result = values[previous_indices(times, target)].copy()
    else:
        result = np.column_stack([np.interp(target, times, values[:, col]) for col in range(values.shape[1])])
    for col in discrete:
        result[:, col] = values[previous_indices(times, target), col]
    return result


def align(episode, config):
    if any(col >= episode.actions.shape[1] for col in config.discrete_action_indices):
        raise InvalidEpisode("Discrete action index exceeds action dimension")
    reference = config.reference_camera or sorted(episode.cameras)[0]
    if reference not in episode.cameras:
        raise InvalidEpisode(f"Reference camera missing: {reference}")
    timelines = [episode.state_time, episode.action_time, *episode.camera_times.values()]
    present = sum(value is not None for value in timelines)
    if not present:
        length = len(episode.state)
        if any(len(value) != length for value in [episode.actions, *episode.cameras.values()]):
            raise InvalidEpisode("Unequal stream lengths without timestamps; supply explicit sampling rates")
        return {"state": episode.state, "actions": episode.actions, "timestamps": None,
                "camera_indices": {key: np.arange(length) for key in episode.cameras},
                "state_previous_indices": np.arange(length), "action_previous_indices": np.arange(length),
                "metadata": {"mode": "index_only", "reference_camera": reference, "dropped_reference_frames": 0}}
    if present != len(timelines):
        raise InvalidEpisode("Partial timing information; supply missing timestamps or explicit sampling rates")
    # Generic vector interpolation must never silently interpolate a declared pose.
    for name, semantics, linear in [('state', config.state_semantics, True), ('action', config.action_semantics, config.action_interpolation == 'linear')]:
        if linear and (semantics.get('rotation', 'none') not in ('none', 'unknown') or semantics.get('representation') in ('eef_pose', 'eef_delta', 'quaternion', 'se3')):
            raise InvalidEpisode(f'{name}: pose-aware interpolation not implemented; use a dedicated adapter')
    timeline = episode.camera_times[reference]
    start, end = max(t[0] for t in timelines), min(t[-1] for t in timelines)
    keep = (timeline >= start) & (timeline <= end)
    keep &= bracket_valid(episode.state_time, timeline, config.max_gap_seconds)
    keep &= bracket_valid(episode.action_time, timeline, config.max_gap_seconds)
    indices = {}
    for name, times in episode.camera_times.items():
        idx = previous_indices(times, timeline)
        safe = np.clip(idx, 0, len(times)-1)
        keep &= (idx >= 0) & ((timeline-times[safe]) <= config.max_camera_delta_seconds)
        indices[name] = safe
    target = timeline[keep]
    if len(target) < config.min_frames:
        raise InvalidEpisode("Insufficient overlap after gap/tolerance filtering")
    mode = "assumed_rate" if any(value.startswith("assumed_fps") for value in episode.time_sources.values()) else "recorded_timestamps"
    return {
        "state": resample(episode.state_time, episode.state, target),
        "actions": resample(episode.action_time, episode.actions, target, config.action_interpolation, config.discrete_action_indices),
        "timestamps": target,
        "camera_indices": {name: idx[keep] for name, idx in indices.items()},
        "state_previous_indices": previous_indices(episode.state_time, target),
        "action_previous_indices": previous_indices(episode.action_time, target),
        "metadata": {"mode": mode, "reference_camera": reference, "dropped_reference_frames": int((~keep).sum()), "overlap_seconds": [float(start), float(end)], "state_interpolation": "linear", "action_interpolation": config.action_interpolation, "discrete_action_interpolation": "previous", "camera_sampling": "previous"},
    }
