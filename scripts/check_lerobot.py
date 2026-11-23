"""Read actual LeRobot batches and verify future actions stay episode-local."""
import argparse
import json
from pathlib import Path
import torch
from lerobot.datasets.lerobot_dataset import LeRobotDataset

p = argparse.ArgumentParser()
p.add_argument('--root', required=True)
p.add_argument('--horizon', type=int, default=50)
a = p.parse_args()
receipt = json.loads((Path(a.root) / 'trajguard_export.json').read_text())
c = receipt['config']
ds = LeRobotDataset(c['repo_id'], root=a.root, video_backend='pyav',
    delta_timestamps={'action': [i/c['fps'] for i in range(a.horizon)]})
offset = 0
for episode in receipt['episodes']:
    n = len(episode['artifact_indices'])
    first, last = ds[offset], ds[offset+n-1]
    assert first['action'].shape == (a.horizon, len(c['action_dimensions']))
    assert torch.isfinite(first['action']).all()
    assert last['action_is_pad'][1:].all()
    assert not last['action_is_pad'][0]
    assert torch.allclose(last['action'], last['action'][0].expand_as(last['action']))
    for camera in c['cameras'].values():
        im = first[f'observation.images.{camera}']
        assert im.ndim == 3 and im.shape[0] == 3 and torch.isfinite(im).all()
        assert im.min() >= 0 and im.max() <= 1
    assert first['task'] == episode['task']
    offset += n
batch = next(iter(torch.utils.data.DataLoader(ds, batch_size=2, num_workers=0)))
print(json.dumps({'frames': len(ds), 'episodes': len(receipt['episodes']),
    'batch': {k: list(v.shape) for k, v in batch.items() if isinstance(v, torch.Tensor)}}, indent=2))
