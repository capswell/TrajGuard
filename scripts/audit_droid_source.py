"""Compare every imported DROID frame against its official TFDS source step."""
import argparse
import json
from pathlib import Path
import h5py
import numpy as np
import tensorflow_datasets as tfds
from trajguard.droid import CAMERAS

p = argparse.ArgumentParser()
p.add_argument('--builder-dir', required=True)
p.add_argument('--hdf5-dir', required=True)
p.add_argument('--report', required=True)
p.add_argument('--limit', type=int, default=2)
a = p.parse_args()
files = {}
for path in Path(a.hdf5_dir).glob('*.hdf5'):
    with h5py.File(path) as h:
        files[h.attrs['source_identity']] = path
results = []
builder = tfds.builder_from_directory(a.builder_dir)
for episode in builder.as_dataset(split=f'train[:{a.limit}]', shuffle_files=False):
    metadata = tfds.as_numpy(episode['episode_metadata'])
    identity = json.dumps({k: v.decode() if isinstance(v, bytes) else str(v) for k,v in metadata.items()}, sort_keys=True)
    with h5py.File(files[identity]) as h:
        count = 0
        for i, step in enumerate(tfds.as_numpy(episode['steps'])):
            for parent, target in [('observation', 'observations/qpos'), ('action_dict', 'action')]:
                expected = np.concatenate([step[parent]['joint_position'], step[parent]['gripper_position']])
                np.testing.assert_array_equal(expected, h[target][i])
            for camera in CAMERAS:
                np.testing.assert_array_equal(step['observation'][camera], h[f'observations/images/{camera}'][i])
            assert step['language_instruction'].decode() == h['instruction'][()].decode()
            count += 1
        assert count == len(h['action'])
        results.append({'source_identity': json.loads(identity), 'frames': count, 'all_vectors_images_instructions_equal': True})
Path(a.report).write_text(json.dumps({'builder': builder.info.full_name, 'episodes': results}, indent=2))
print(json.dumps({'source_audit': 'passed', 'frames':sum(r['frames'] for r in results)}))
