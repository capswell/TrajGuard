"""Rules describe defined checks, never claim semantic task success."""
import numpy as np
from .adapters import InvalidEpisode


def quality(state, actions, times, config):
    if config.checked_state_indices:
        if max(config.checked_state_indices) >= state.shape[1]:
            raise InvalidEpisode("checked_state_indices exceeds state dimension")
        state = state[:, list(config.checked_state_indices)]
    findings = []
    def issue(rule, severity, message, frames=None):
        findings.append({"rule": rule, "severity": severity, "message": message, "frames": frames or []})
    if min(len(state), len(actions)) < config.min_frames:
        issue("min_frames", "reject", f"Requires >= {config.min_frames} state/action frames")
    distances = np.linalg.norm(np.diff(state, axis=0), axis=1)
    path = float(distances.sum())
    metrics = {"state_frames": len(state), "action_frames": len(actions), "path_length": path,
               "net_displacement": float(np.linalg.norm(state[-1]-state[0])),
               "active_fraction": float(np.mean(distances > 1e-8)), "state_unit": config.state_unit,
               "checked_state_indices": list(config.checked_state_indices) or "all"}
    if path < config.min_path_length and not config.allow_stationary:
        issue("low_motion", "review", "Low cumulative motion: review task context before excluding this episode")
    if times is not None:
        speed = np.abs(np.diff(state, axis=0)) / np.diff(times)[:, None]
        metrics["max_speed"] = float(speed.max())
        metrics["speed_unit"] = f"{config.state_unit}/s"
        if config.max_speed is not None:
            bad = np.flatnonzero(np.any(speed > config.max_speed, axis=1)) + 1
            if len(bad):
                issue("speed_limit", "reject", f"Configured speed limit {config.max_speed} exceeded", [int(i) for i in bad])
    elif config.max_speed is not None:
        issue("speed_unverifiable", "reject", "Speed threshold configured but timestamps/sampling rate unavailable")
    status = "rejected" if any(item["severity"] == "reject" for item in findings) else "review" if findings else "accepted"
    return status, findings, metrics
