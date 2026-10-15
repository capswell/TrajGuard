"""Explicit data semantics; no inferred joint/gripper units or sampling rates."""
from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class Config:
    min_frames: int = 15
    min_path_length: float = 0.01
    allow_stationary: bool = False
    max_speed: float | None = None
    state_unit: str = "unknown"
    checked_state_indices: tuple[int, ...] = ()
    state_fps: float | None = None
    action_fps: float | None = None
    camera_fps: float | None = None
    timestamp_scale: float = 1.0
    state_timestamp_path: str | None = None
    action_timestamp_path: str | None = None
    camera_timestamp_paths: dict[str, str] = field(default_factory=dict)
    reference_camera: str | None = None
    discrete_action_indices: tuple[int, ...] = ()
    action_interpolation: str = "previous"
    max_gap_seconds: float = 0.2
    max_camera_delta_seconds: float = 0.05
    chunk_frames: int = 8
    decoded_color_order: str = "unknown"

    def validate(self):
        if type(self.allow_stationary) is not bool:
            raise ValueError("allow_stationary must be a JSON boolean")
        if not isinstance(self.state_unit, str) or not self.state_unit.strip():
            raise ValueError("state_unit must be a nonempty string")
        if not isinstance(self.camera_timestamp_paths, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not v for k, v in self.camera_timestamp_paths.items()):
            raise ValueError("camera_timestamp_paths must map camera names to nonempty paths")
        if type(self.min_frames) is not int or type(self.chunk_frames) is not int or self.min_frames < 2 or self.chunk_frames < 1:
            raise ValueError("min_frames must be >=2 and chunk_frames >=1")
        for name in ("min_path_length", "max_gap_seconds", "max_camera_delta_seconds", "timestamp_scale", "state_fps", "action_fps", "camera_fps", "max_speed"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not math.isfinite(value) or value < 0 or (name != "min_path_length" and value == 0)):
                raise ValueError(f"Invalid positive setting: {name}")
        if self.action_interpolation not in ("previous", "linear"):
            raise ValueError("action_interpolation must be previous or linear")
        if self.decoded_color_order not in ("unknown", "rgb", "bgr"):
            raise ValueError("decoded_color_order must be unknown, rgb, or bgr")
        if self.max_speed is not None and self.state_unit == "unknown":
            raise ValueError("Specify state_unit when configuring max_speed")
        for name in ("discrete_action_indices", "checked_state_indices"):
            indices = getattr(self, name)
            if any(type(i) is not int or i < 0 for i in indices) or len(set(indices)) != len(indices):
                raise ValueError(f"{name} must contain unique nonnegative integers")
        return self

    def as_dict(self):
        return asdict(self)

    @classmethod
    def load(cls, filename=None):
        raw = json.loads(Path(filename).read_text(encoding="utf-8")) if filename else {}
        for name in ("discrete_action_indices", "checked_state_indices"):
            if name in raw:
                raw[name] = tuple(raw[name])
        return cls(**raw).validate()
