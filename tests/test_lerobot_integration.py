"""Requires the optional real LeRobot 0.6.1 environment; no fake dataset writer."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import h5py
import numpy as np
import pytest
from conftest import make_episode
from trajguard.config import Config
from trajguard.pipeline import run
from trajguard.lerobot_export import export


@pytest.mark.skipif(importlib.util.find_spec('lerobot') is None, reason='requires lerobot==0.6.1')
def test_real_writer_reader_and_integrity(tmp_path):
    raw = tmp_path / 'raw'
    raw.mkdir()
    for i in range(2):
        with h5py.File(raw / f'{i}.hdf5', 'w') as h:
            make_episode(h)
            h.create_dataset('observations/images/wrist', data=h['observations/images/cam_high'][:])
            h.create_dataset('timestamps/images/wrist', data=h['timestamps/images/cam_high'][:])
    run(raw, tmp_path/'qc', Config(), 1, False)
    c = json.loads((Path(__file__).parents[1]/'configs/lerobot_fixture.json').read_text())
    c['cameras']['wrist'] = 'wrist'
    c['colors']['wrist'] = 'rgb'
    cfg = tmp_path/'export.json'
    cfg.write_text(json.dumps(c))
    manifest = tmp_path/'qc/manifest.json'
    target = tmp_path/'dataset'
    result = export(manifest, target, cfg)
    assert len(result['episodes']) == 2
    assert export(manifest, target, cfg, True)['signature'] == result['signature']
    assert (target/'trajguard_train_stats.json').is_file()
    with pytest.raises(ValueError, match='Target exists'):
        export(manifest, target, cfg)
    script = Path(__file__).parents[1]/'scripts/check_lerobot.py'
    subprocess.run([sys.executable, str(script), '--root', str(target)], check=True, capture_output=True)
    (target/'meta/info.json').write_text('{}')
    with pytest.raises(ValueError, match='Target exists'):
        export(manifest, target, cfg, True)
