import json
import numpy as np
import pytest

from trajguard.config import Config
from trajguard.labels import template, validate_labels
from trajguard.pipeline import run
from trajguard.quality import quality


def test_exclude_gripper_from_joint_speed_threshold():
    state = np.column_stack([np.arange(30)*.001, np.arange(30)%2])
    cfg = Config(checked_state_indices=(0,), state_unit="rad", max_speed=1)
    assert quality(state, state, np.arange(30)*.01, cfg)[0] == "accepted"
    assert quality(state, state, np.arange(30)*.01, Config(state_unit="rad", max_speed=1))[0] == "rejected"


@pytest.mark.parametrize("mutation", ["stale", "no_reviewer", "no_model", "duplicate"])
def test_labels_reject_bad_provenance(episode_file, tmp_path, mutation):
    out = tmp_path / "out"
    run(episode_file, out, Config())
    candidates = tmp_path / "candidates.json"
    template(out / "manifest.json", candidates)
    data = json.loads(candidates.read_text())
    if mutation == "stale":
        data[0]["signature"] = "old"
    elif mutation == "no_reviewer":
        data[0].update(review_status="reviewed", candidate_instruction="Move cup")
    elif mutation == "no_model":
        data[0]["provider"] = "vlm"
    else:
        data.append(data[0])
    candidates.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        validate_labels(out / "manifest.json", candidates, tmp_path / "labels.json")


def test_label_template_leaves_original_unchanged(episode_file, tmp_path):
    from trajguard.storage import fingerprint
    out = tmp_path / "out"
    m = run(episode_file, out, Config())
    artifact = next(iter(m["jobs"].values()))["artifact"]
    old_hash = fingerprint(artifact)
    candidates = tmp_path / "candidates.json"
    assert template(out / "manifest.json", candidates) == 1
    assert validate_labels(out / "manifest.json", candidates, tmp_path / "labels.json") == 1
    assert fingerprint(artifact) == old_hash
    assert json.loads((tmp_path / "labels.json").read_text())["semantic_accuracy_verified"] is False


@pytest.mark.parametrize("setting", [{"chunk_frames": 1.5}, {"min_frames": True}, {"checked_state_indices": (True,)}, {"checked_state_indices": (1, 1)}, {"allow_stationary": "false"}, {"camera_timestamp_paths": []}, {"state_unit": ""}])
def test_config_rejects_noninteger_and_duplicate_indices(setting):
    with pytest.raises(ValueError):
        Config(**setting).validate()
