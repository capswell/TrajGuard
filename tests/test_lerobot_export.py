import io
import numpy as np
import pytest
from PIL import Image
from trajguard.lerobot_export import segments, split_for, decode


def test_gaps_split_future_action_boundaries():
    groups = segments(np.array([0, .1, .2, 1, 1.1]), 5, 10, 1e-6)
    assert [g.tolist() for g in groups] == [[0, 1, 2], [3, 4]]


def test_accumulated_clock_drift_rejected():
    with pytest.raises(ValueError, match='clock drift'):
        segments(np.arange(20) * .10005, 20, 10, 1e-4)


@pytest.mark.parametrize('times', [[0, .1, .15], [0, 0, .1], [0, float('nan'), .2]])
def test_invalid_timing(times):
    with pytest.raises(ValueError):
        segments(times, 3, 10, 1e-5)


def test_split_stable_across_processing_versions():
    assert split_for('sha:episode', 7, .2) == split_for('sha:episode', 7, .2)
    assert {split_for(str(i), 0, .5) for i in range(100)} == {'train', 'validation'}


def test_jpeg_color_and_corruption():
    buf = io.BytesIO()
    Image.new('RGB', (16, 12), (240, 10, 20)).save(buf, format='JPEG')
    payload = np.frombuffer(buf.getvalue(), np.uint8)
    rgb = decode(payload, 'rgb')
    bgr = decode(payload, 'bgr')
    np.testing.assert_array_equal(rgb[..., ::-1], bgr)
    with pytest.raises(Exception):
        decode(np.array([1, 2, 3], np.uint8), 'rgb')
    with pytest.raises(ValueError):
        decode(payload, 'unknown')
