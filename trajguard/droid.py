"""DROID RLDS/TFDS -> ALOHA-shaped input, without inferring a clock."""
import hashlib
import json
from pathlib import Path
import h5py
import numpy as np


CAMERAS = ('exterior_image_1_left', 'exterior_image_2_left', 'wrist_image_left')


def convert_episode(steps, metadata, output):
    """Consume TFDS numpy steps; retain joint-position commands, not action[7]."""
    output = Path(output)
    if output.exists():
        raise ValueError('DROID target exists')
    identity = {k: (v.decode() if isinstance(v, bytes) else str(v)) for k, v in metadata.items()}
    rows = list(steps)  # One bounded episode, not the full dataset.
    if len(rows) < 2 or not bool(rows[0]['is_first']) or not bool(rows[-1]['is_last']):
        raise ValueError('Incomplete RLDS episode')
    def vector(row, parent):
        group = row[parent]
        joint = np.asarray(group['joint_position']).reshape(-1)
        gripper = np.asarray(group['gripper_position']).reshape(-1)
        if joint.shape != (7,) or gripper.shape != (1,):
            raise ValueError('DROID joint_position[7] and gripper_position[1] required')
        value = np.concatenate([joint, gripper])
        if not np.isfinite(value).all():
            raise ValueError('DROID nonfinite state/action')
        return value
    state = np.stack([vector(r, 'observation') for r in rows])
    action = np.stack([vector(r, 'action_dict') for r in rows])
    texts = [r['language_instruction'].decode() if isinstance(r['language_instruction'], bytes) else str(r['language_instruction']) for r in rows]
    if not texts[0].strip() or len(set(texts)) != 1:
        raise ValueError('Instruction missing or changes within episode')
    cameras = {k: np.stack([r['observation'][k] for r in rows]) for k in CAMERAS}
    for k, value in cameras.items():
        if value.dtype != np.uint8 or value.ndim != 4 or value.shape[-1] != 3:
            raise ValueError(f'{k}: uint8 RGB required')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.incomplete')
    if temporary.exists():
        raise ValueError('Incomplete DROID conversion exists')
    with h5py.File(temporary, 'w') as h:
        h.create_dataset('observations/qpos', data=state)
        h.create_dataset('action', data=action)
        h.create_dataset('instruction', data=texts[0], dtype=h5py.string_dtype())
        for key, value in cameras.items():
            ds = h.create_dataset(f'observations/images/{key}', data=value, compression='lzf', chunks=(1, *value.shape[1:]))
            ds.attrs['decoded_color_order'] = 'rgb'
        h.attrs['source_format'] = 'DROID RLDS/TFDS official schema'
        h.attrs['source_identity'] = json.dumps(identity, sort_keys=True)
        h.attrs['action_representation'] = '7 joint positions + commanded gripper position; no delta conversion'
        h.attrs['robot_type'] = 'franka'
        h.attrs['timing'] = 'index_only; release steps have no recorded timestamps'
    temporary.replace(output)


def import_tfds(builder_dir, output, limit=2):
    import tensorflow_datasets as tfds
    builder = tfds.builder_from_directory(builder_dir)
    for i, episode in enumerate(builder.as_dataset(split=f'train[:{limit}]', shuffle_files=False)):
        if i >= limit:
            break
        metadata = tfds.as_numpy(episode['episode_metadata'])
        key = hashlib.sha256(repr(sorted(metadata.items())).encode()).hexdigest()[:24]
        convert_episode(tfds.as_numpy(episode['steps']), metadata, Path(output) / f'{key}.hdf5')
