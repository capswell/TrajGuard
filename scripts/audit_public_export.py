"""Independent source/artifact/LeRobot checks on downloaded public samples."""
import argparse
import json
from pathlib import Path
import h5py
import numpy as np
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from trajguard.lerobot_export import decode

p = argparse.ArgumentParser()
p.add_argument('--root', required=True)
p.add_argument('--report', required=True)
p.add_argument('--manifest', required=True)
a = p.parse_args()
root = Path(a.root)
r = json.loads((root/'trajguard_export.json').read_text())
c = r['config']
ds = LeRobotDataset(c['repo_id'], root=root, video_backend='pyav', delta_timestamps={'action': [i/c['fps'] for i in range(50)]})
results = []
offset = 0
for episode in r['episodes']:
    provenance = episode['original_provenance']
    m = json.loads(Path(a.manifest).read_text())
    job = m['jobs'][episode['job_id']]
    indices = np.array(episode['artifact_indices'])
    with h5py.File(job['artifact']) as h, h5py.File(provenance['source']) as src:
        np.testing.assert_array_equal(src['observations/qpos'][:], h['state'][:])
        np.testing.assert_array_equal(src['action'][:], h['actions'][:])
        row = {'job': episode['job_id'], 'frames': len(indices), 'task': episode['task'], 'checks': [], 'images': []}
        for i in sorted(set([0, len(indices)//2, len(indices)-1])):
            sample = ds[offset+i]
            assert sample['task'] == episode['task']
            np.testing.assert_allclose(sample['observation.state'].numpy(), h['state'][indices[i]], atol=1e-6, rtol=1e-6)
            expected = np.asarray([h['actions'][indices[min(i+j, len(indices)-1)]] for j in range(50)])
            np.testing.assert_allclose(sample['action'].numpy(), expected, atol=1e-6, rtol=1e-6)
            np.testing.assert_array_equal(sample['action_is_pad'].numpy(), np.arange(50)+i >= len(indices))
            for camera, target in c['cameras'].items():
                source_index = int(h[f'source_indices/images/{camera}'][indices[i]])
                raw = src[f'observations/images/{camera}'][source_index]
                payload = h[f'images/{camera}'][indices[i]]
                np.testing.assert_array_equal(raw, payload)
                expected_image = decode(payload, c['colors'][camera])
                actual = sample[f'observation.images.{target}'].numpy().transpose(1,2,0)*255
                mae = float(np.abs(actual-expected_image.astype(float)).mean())
                assert mae < (12 if c['use_videos'] else .01), (camera, i, mae)
                row['images'].append({'frame': int(indices[i]), 'camera': camera, 'mae_rgb_255': mae})
            row['checks'].append(int(indices[i]))
        results.append(row)
    offset += len(indices)
assert offset == len(ds)
video_counts = {}
if c['use_videos']:
    import av
    for camera in c['cameras'].values():
        total = 0
        for path in (root/'videos'/f'observation.images.{camera}').rglob('*.mp4'):
            with av.open(str(path)) as container:
                for frame in container.decode(video=0):
                    assert frame.width > 0 and frame.height > 0
                    total += 1
        assert total == len(ds), (camera, total, len(ds))
        video_counts[camera] = total
Path(a.report).write_text(json.dumps({'dataset':c['repo_id'], 'frames':len(ds), 'episodes':results,
    'decoded_video_frames_by_camera': video_counts,
    'scope':'All source/artifact vector values; sampled LeRobot states, 50-step actions, masks, tasks and images. Video RGB comparison allows lossy encoding.'},indent=2))
print(json.dumps({'dataset':c['repo_id'],'frames':len(ds),'episodes':len(results),'audit':'passed'}))
