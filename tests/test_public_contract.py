import json
from dataclasses import replace
from pathlib import Path

import h5py
import pytest

from trajguard.adapters import read_episode, InvalidEpisode
from trajguard.alignment import align
from trajguard.config import Config
from trajguard.pipeline import run
from trajguard.lerobot_export import validate_config


def test_unknown_semantics_are_diagnosed_and_provenance_survives(episode_file, tmp_path):
    with h5py.File(episode_file, 'a') as h:
        h.attrs['source_identity'] = 'stable-original-episode'
    result = run(episode_file, tmp_path/'out', Config(), 1, False)
    job = next(iter(result['jobs'].values()))
    assert job['status'] == 'accepted' and len(job['diagnostics']) == 2
    assert 'semantics unspecified' in (tmp_path/'out/report.html').read_text(encoding='utf-8')
    with h5py.File(job['artifact']) as h:
        assert json.loads(h.attrs['provenance'])['source_metadata']['source_identity'] == 'stable-original-episode'
        assert json.loads(h.attrs['semantics']) == {'state': {}, 'action': {}}


def test_camera_color_and_semantic_dimensions(episode_file, tmp_path):
    c = Config(camera_color_orders={'cam_high': 'bgr'}, state_semantics={'representation': 'joint_position', 'dimensions': [{'name': 'q0', 'unit': 'rad'}, {'name': 'q1', 'unit': 'rad'}]})
    job = next(iter(run(episode_file, tmp_path/'out', c, 1, False)['jobs'].values()))
    with h5py.File(job['artifact']) as h:
        assert h['images/cam_high'].attrs['decoded_color_order'] == 'bgr'
    with h5py.File(episode_file) as h, pytest.raises(InvalidEpisode, match='dimensions'):
        read_episode(h, replace(c, state_semantics={'dimensions': [{'name': 'wrong', 'unit': 'm'}]}))


def test_declared_pose_cannot_use_generic_linear_interpolation(episode_file):
    c = Config(state_semantics={'representation': 'eef_pose', 'rotation': 'quaternion'})
    with h5py.File(episode_file) as h, pytest.raises(InvalidEpisode, match='pose-aware'):
        align(read_episode(h, c), c)


@pytest.mark.parametrize('kwargs', [dict(state_semantics={'frequency': 0}), dict(action_semantics={'typo': 'x'}), dict(camera_color_orders={'high': 'guess'})])
def test_invalid_semantics(kwargs):
    with pytest.raises(ValueError):
        Config(**kwargs).validate()


def test_export_rejects_unknown_or_missing_configuration():
    with pytest.raises(ValueError, match='configuration requires'):
        validate_config({})
    c = json.loads((Path(__file__).parents[1]/'configs/lerobot_fixture.json').read_text())
    c['action_semantics']['coordinate_frame'] = 'unknown'
    with pytest.raises(ValueError, match='coordinate_frame'):
        validate_config(c)
    c['action_semantics']['coordinate_frame'] = 'fixture'
    c['colors']['cam_high'] = 'unknown'
    with pytest.raises(ValueError, match='colors'):
        validate_config(c)
