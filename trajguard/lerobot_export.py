"""Strict fixed-rate export through LeRobot 0.6.1's public writer API."""
import hashlib
import io
import json
import os
import time
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError

import h5py
import numpy as np

from .storage import atomic_json, fingerprint


def segments(times, count, fps, tolerance):
    if times is None:
        return [np.arange(count)]
    t = np.asarray(times, dtype=float)
    if t.shape != (count,) or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError('Invalid export timestamps')
    delta = np.diff(t)
    # Only exact fixed-rate islands are exported. No pose interpolation or invented frames.
    gap = delta > 1 / fps + tolerance
    if np.any((~gap) & (np.abs(delta - 1 / fps) > tolerance)):
        raise ValueError('Nonuniform or faster sampling: resample upstream with verified semantics')
    islands = [x for x in np.split(np.arange(count), np.flatnonzero(gap) + 1) if len(x) >= 2]
    for indices in islands:
        if np.any(np.abs((t[indices] - t[indices[0]]) - np.arange(len(indices))/fps) > tolerance):
            raise ValueError('Accumulated clock drift exceeds fixed-rate tolerance')
    return islands


def split_for(identity, seed, validation_fraction):
    value = int(hashlib.sha256(f'{seed}:{identity}'.encode()).hexdigest()[:16], 16) / 2**64
    return 'validation' if value < validation_fraction else 'train'


def decode(row, color):
    from PIL import Image
    array = np.asarray(row)
    if array.ndim == 3:
        if array.dtype != np.uint8 or array.shape[-1] != 3:
            raise ValueError('Expected uint8 HWC image')
    else:
        with Image.open(io.BytesIO(array.tobytes())) as image:
            image.load()
            if image.mode != 'RGB':
                raise ValueError(f'Expected RGB JPEG, found {image.mode}')
            array = np.array(image)
    if color not in ('rgb', 'bgr'):
        raise ValueError('Explicit decoded color semantics required')
    return array[..., ::-1].copy() if color == 'bgr' else array


def validate_config(c):
    required = {'fps', 'cameras', 'colors', 'state_dimensions', 'action_dimensions', 'action_semantics', 'repo_id', 'robot_type'}
    if not isinstance(c, dict) or required - c.keys():
        raise ValueError(f'Export configuration requires {sorted(required)}')
    if type(c['fps']) is not int or c['fps'] <= 0:
        raise ValueError('fps must be a positive integer')
    if not 0 <= c.get('validation_fraction', .2) < 1:
        raise ValueError('validation_fraction must be in [0,1)')
    if not np.isfinite(c.get('time_tolerance', 1e-4)) or not 0 < c.get('time_tolerance', 1e-4) < .5/c['fps']:
        raise ValueError('time_tolerance must be positive')
    if not c['cameras'] or len(set(c['cameras'].values())) != len(c['cameras']):
        raise ValueError('Camera mapping must be nonempty and one-to-one')
    if any(not isinstance(name, str) or not name.isidentifier() for name in c['cameras'].values()):
        raise ValueError('Target camera names must be identifiers')
    if any(c['colors'].get(camera) not in ('rgb', 'bgr') for camera in c['cameras']):
        raise ValueError('Every camera needs confirmed rgb/bgr colors')
    for k in ('state_dimensions', 'action_dimensions'):
        rows = c[k]
        if not rows or any(not all(isinstance(r.get(f), str) and r[f].strip() for f in ('name', 'unit')) for r in rows):
            raise ValueError(f'{k}: each dimension needs name and unit')
        if any(r['unit'] == 'unknown' for r in rows) or len({r['name'] for r in rows}) != len(rows):
            raise ValueError(f'{k}: confirmed units and unique dimension names required')
    for key in ('representation', 'coordinate_frame', 'rotation', 'gripper', 'time_interval', 'control_frequency'):
        if not c['action_semantics'].get(key) or c['action_semantics'][key] == 'unknown':
            raise ValueError(f'action_semantics.{key} required')


def export(manifest_path, output, config_path, resume=False):
    started = time.perf_counter()
    c = json.loads(Path(config_path).read_text(encoding='utf-8'))
    validate_config(c)
    m = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    selected = sorted((k, j) for k, j in m['jobs'].items() if j['status'] == 'accepted')
    if not selected:
        raise ValueError('Manifest has no accepted episodes')
    output = Path(output).resolve()
    signature = hashlib.sha256(json.dumps([fingerprint(__file__), c, selected], sort_keys=True).encode()).hexdigest()
    receipt = output / 'trajguard_export.json'
    if output.exists():
        if resume and receipt.is_file():
            old = json.loads(receipt.read_text())
            if old['signature'] == signature and all((output / p).is_file() and fingerprint(output / p) == digest for p, digest in old['files'].items()) and all(fingerprint(j['artifact']) == j['artifact_sha256'] for _, j in selected):
                return old
        raise ValueError('Target exists or is incomplete/changed; choose a new target (never appended implicitly)')
    stage = output.with_name(output.name + '.incomplete')
    stage.parent.mkdir(parents=True, exist_ok=True)
    if stage.exists():
        raise ValueError(f'Incomplete export at {stage}; inspect it, then use a new target')
    try:
        installed = version('lerobot')
    except PackageNotFoundError:
        raise ValueError('Optional integration absent: use Python >=3.12 and pip install -e ".[lerobot]"') from None
    if installed != '0.6.1':
        raise ValueError('This exporter requires lerobot==0.6.1')
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.configs.video import RGBEncoderConfig
    features = {key: {'dtype': 'float32', 'shape': (len(c[dim]),), 'names': [d['name'] for d in c[dim]]}
                for key, dim in [('observation.state', 'state_dimensions'), ('action', 'action_dimensions')]}
    writer = None
    mapping = []
    input_frames = 0
    training = {'state': [], 'action': []}
    try:
        for job_id, job in selected:
            if fingerprint(job['artifact']) != job['artifact_sha256']:
                raise ValueError(f'{job_id}: artifact hash mismatch')
            with h5py.File(job['artifact']) as h:
                provenance = json.loads(h.attrs['provenance'])
                identity = f"{provenance['source_sha256']}:{provenance['episode']}"
                metadata = provenance.get('source_metadata', {})
                if metadata.get('source_identity'):
                    identity = metadata['source_identity']
                split = split_for(identity, c.get('seed', 0), c.get('validation_fraction', .2))
                raw = h['instruction'][()]
                task = raw.decode() if isinstance(raw, bytes) else str(raw)
                task = task.strip() or c.get('fallback_instruction', '').strip()
                if not task:
                    raise ValueError(f'{job_id}: missing instruction; supply a verified fallback_instruction')
                state, actions = h['state'][:], h['actions'][:]
                input_frames += len(state)
                for key, array, dim in [('state', state, 'state_dimensions'), ('actions', actions, 'action_dimensions')]:
                    if array.shape != (len(state), len(c[dim])) or not np.isfinite(array).all():
                        raise ValueError(f'{job_id}: invalid {key} dimensions/values')
                    if not np.isfinite(array.astype('float32')).all():
                        raise ValueError('float32 overflow')
                mode = json.loads(h.attrs['alignment'])['mode']
                if mode == 'index_only' and not c.get('index_fps_basis'):
                    raise ValueError('index_only requires explicit index_fps_basis; FPS is an assumption')
                times = h['timestamps'][:] if 'timestamps' in h else None
                if mode not in ('index_only', 'recorded_timestamps', 'assumed_rate') or (mode == 'index_only') != (times is None):
                    raise ValueError('Time mode and timestamp presence disagree')
                islands = segments(times, len(state), c['fps'], c.get('time_tolerance', 1e-4))
                for camera, name in c['cameras'].items():
                    if f'images/{camera}' not in h or len(h[f'images/{camera}']) != len(state):
                        raise ValueError(f'{job_id}: camera missing or length mismatch: {camera}')
                    image = decode(h[f'images/{camera}'][0], c['colors'][camera])
                    declared = h[f'images/{camera}'].attrs.get('decoded_color_order', 'unknown')
                    if declared != 'unknown' and declared != c['colors'][camera]:
                        raise ValueError(f'{camera}: export color contradicts artifact declaration')
                    feature = {'dtype': 'video' if c.get('use_videos', True) else 'image', 'shape': image.shape, 'names': ['height', 'width', 'channels']}
                    key = f'observation.images.{name}'
                    if key in features and features[key] != feature:
                        raise ValueError('Camera resolution changed across episodes')
                    features[key] = feature
                if writer is None:
                    writer = LeRobotDataset.create(repo_id=c['repo_id'], root=stage, fps=c['fps'], features=features,
                        robot_type=c['robot_type'], use_videos=c.get('use_videos', True),
                        rgb_encoder=RGBEncoderConfig(vcodec=c.get('video_codec', 'h264'), crf=c.get('video_crf', 18)), encoder_threads=1)
                for indices in islands:
                    if split == 'train':
                        training['state'].append(state[indices])
                        training['action'].append(actions[indices])
                    for i in indices:
                        frame = {'observation.state': state[i].astype('float32'), 'action': actions[i].astype('float32'), 'task': task}
                        for camera, name in c['cameras'].items():
                            key = f'observation.images.{name}'
                            image = decode(h[f'images/{camera}'][i], c['colors'][camera])
                            if image.shape != features[key]['shape']:
                                raise ValueError(f'{camera}: changing image dimensions')
                            frame[key] = image
                        writer.add_frame(frame)
                    writer.save_episode(parallel_encoding=False)
                    mapping.append({'lerobot_episode': len(mapping), 'job_id': job_id, 'source_identity': identity,
                        'signature': job['signature'], 'split': split, 'task': task, 'time_mode': mode,
                        'source_timestamps': times[indices].tolist() if times is not None else None,
                        'artifact_indices': indices.tolist(), 'source_indices': {k: h[f'source_indices/images/{k}'][indices].tolist() for k in c['cameras']},
                        'original_provenance': provenance})
        if writer is None or not mapping:
            raise ValueError('No continuous segments of >=2 frames')
        writer.finalize()
        reader = LeRobotDataset(c['repo_id'], root=stage, video_backend='pyav')
        if len(reader) != sum(len(r['artifact_indices']) for r in mapping):
            raise ValueError('Reader frame count mismatch')
        reader[0]
        train_stats = {}
        for key, blocks in training.items():
            if blocks:
                values = np.concatenate(blocks)
                train_stats[key] = {'count': len(values), 'mean': values.mean(0).tolist(),
                    'std': values.std(0).tolist(), 'min': values.min(0).tolist(), 'max': values.max(0).tolist(),
                    'q01': np.quantile(values, .01, axis=0).tolist(), 'q99': np.quantile(values, .99, axis=0).tolist()}
        atomic_json(stage / 'trajguard_train_stats.json', {'split': 'train', 'seed': c.get('seed', 0), 'stats': train_stats})
        result = {'signature': signature, 'config': c, 'episodes': mapping,
            'elapsed_seconds': time.perf_counter() - started, 'input_episodes': len(selected),
            'input_frames': input_frames, 'output_frames': sum(len(r['artifact_indices']) for r in mapping),
            'dropped_frames': input_frames - sum(len(r['artifact_indices']) for r in mapping),
            'extra_segments': len(mapping) - len(selected),
            'quality_counts': {s: sum(j['status'] == s for j in m['jobs'].values()) for s in ('accepted', 'review', 'rejected', 'failed')},
            'normalization': 'LeRobot writer stats are whole-export; training-only vector stats in trajguard_train_stats.json. Explicit model processor wiring required. No values normalized here.',
            'files': {str(p.relative_to(stage)): fingerprint(p) for p in stage.rglob('*') if p.is_file()}}
        atomic_json(stage / 'trajguard_export.json', result)
        del reader
        os.replace(stage, output)
        return result
    except BaseException:
        if writer is not None:
            try:
                writer.finalize()
            except Exception:
                pass  # Preserve the original failure; incomplete directory is never published.
        raise
