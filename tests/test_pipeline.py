import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from conftest import make_episode
from trajguard.config import Config
from trajguard.pipeline import run
from trajguard.quality import quality


def only_job(manifest):
    return next(iter(manifest["jobs"].values()))


def test_jpeg_bytes_and_instruction_preserved(episode_file, tmp_path):
    m = run(episode_file, tmp_path / "out", Config())
    j = only_job(m)
    assert j["status"] == "accepted"
    with h5py.File(episode_file, "r") as raw, h5py.File(j["artifact"], "r") as clean:
        np.testing.assert_array_equal(raw["observations/images/cam_high"][:], clean["images/cam_high"][:])
        assert clean["instruction"][()].decode() == "Move the object"
        assert clean["images/cam_high"].ndim == 2
        assert clean["images/cam_high"].attrs["decoded_color_order"] == "unknown"
        assert json.loads(clean.attrs["provenance"])["source_sha256"]
        assert clean["source_indices/images/cam_high"].shape == (30,)


def test_loop_motion_not_rejected_as_stationary():
    state = np.sin(np.linspace(0, 2*np.pi, 100))[:, None]
    status, findings, metrics = quality(state, state, None, Config())
    assert status == "accepted"
    assert metrics["net_displacement"] < .01
    assert metrics["path_length"] > 3.9


def test_low_motion_enters_review(tmp_path):
    path = tmp_path / "input.h5"
    with h5py.File(path, "w") as f:
        make_episode(f, stationary=True)
    m = run(path, tmp_path / "out", Config())
    assert only_job(m)["status"] == "review"
    assert "artifact" not in only_job(m)
    assert json.loads((tmp_path / "out/review_queue.json").read_text())[0]["status"] == "review"


def test_speed_divides_by_time_and_uses_declared_units():
    state = np.arange(30)[:, None] * .01
    cfg = Config(max_speed=.5, state_unit="rad")
    status, _, metrics = quality(state, state, np.arange(30)*.01, cfg)
    assert status == "rejected"
    assert metrics["max_speed"] == pytest.approx(1)
    assert metrics["speed_unit"] == "rad/s"


@pytest.mark.parametrize("mutation", ["empty", "single", "nan", "inf"])
def test_malformed_state_rejected(episode_file, tmp_path, mutation):
    with h5py.File(episode_file, "r+") as f:
        if mutation in ("empty", "single"):
            del f["observations/qpos"]
            f.create_dataset("observations/qpos", data=np.zeros((0 if mutation == "empty" else 1, 2)))
        else:
            f["observations/qpos"][0, 0] = np.nan if mutation == "nan" else np.inf
    assert only_job(run(episode_file, tmp_path / "out", Config()))["status"] == "rejected"


def test_resume_checks_output_content_and_configuration(episode_file, tmp_path):
    out = tmp_path / "out"
    first = run(episode_file, out, Config())
    path = Path(only_job(first)["artifact"])
    saved = path.stat().st_mtime_ns
    assert run(episode_file, out, Config(), resume=True)["resumed"] == 1
    assert path.stat().st_mtime_ns == saved
    path.write_bytes(b"corrupt")
    repaired = run(episode_file, out, Config(), resume=True)
    assert repaired["processed"] == 1
    assert h5py.is_hdf5(path)
    assert run(episode_file, out, Config(chunk_frames=2), resume=True)["processed"] == 1


def test_changed_source_invalidates_resume(episode_file, tmp_path):
    out = tmp_path / "out"
    first = only_job(run(episode_file, out, Config()))
    with h5py.File(episode_file, "r+") as f:
        f["observations/qpos"][0, 0] = .01
    second = only_job(run(episode_file, out, Config(), resume=True))
    assert first["signature"] != second["signature"]


def test_multi_episode_failure_isolation_and_process_pool(tmp_path):
    file = tmp_path / "input.h5"
    with h5py.File(file, "w") as handle:
        for index in range(3):
            make_episode(handle.create_group(f"data/demo_{index}"))
        handle["data/demo_1/action"][5, 0] = np.nan
    m = run(file, tmp_path / "out", Config(), workers=2)
    assert len(m["jobs"]) == 3
    assert sorted(j["status"] for j in m["jobs"].values()) == ["accepted", "accepted", "rejected"]


def test_corrupt_file_does_not_block_good_file(episode_file, tmp_path):
    (tmp_path / "broken.h5").write_bytes(b"not hdf5")
    out = tmp_path.parent / (tmp_path.name+"-out")
    m = run(tmp_path, out, Config())
    assert sorted(j["status"] for j in m["jobs"].values()) == ["accepted", "failed"]


def test_report_escapes_untrusted_input(episode_file, tmp_path):
    bad = tmp_path / "<img onerror=alert(1)>.h5"
    # Windows disallows '<' in filenames; test the renderer directly instead.
    from trajguard.report import render_report
    render_report({"jobs": {"x": {"source": "<script>alert(1)</script>", "episode": "/", "status": "failed"}}}, tmp_path / "safe.html")
    html = (tmp_path / "safe.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_output_cannot_be_ingested_again(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        run(tmp_path, tmp_path / "output", Config())
    assert not (tmp_path / "output/.trajguard.lock").exists()


def test_lock_prevents_concurrent_writers(episode_file, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / ".trajguard.lock").write_text("locked")
    with pytest.raises(ValueError, match="locked"):
        run(episode_file, out, Config())
    assert (out / ".trajguard.lock").exists()


@pytest.mark.parametrize("settings", [dict(max_speed=1), dict(chunk_frames=0), dict(state_fps=0), dict(action_interpolation="nearest"), dict(discrete_action_indices=(-1,))])
def test_bad_config(settings):
    with pytest.raises(ValueError):
        Config(**settings).validate()
