import random

import pytest

from handcursor.config import Config, ConfigError, load_config
from handcursor.smoothing import OneEuroFilter


def test_filter_steadies_jitter_on_a_still_hand():
    rng = random.Random(1)
    f = OneEuroFilter(min_cutoff=1.0, beta=0.01)
    outputs = [f.update(500 + rng.uniform(-3, 3), i / 30) for i in range(120)]
    assert max(outputs[30:]) - min(outputs[30:]) < 3


def test_filter_catches_up_quickly_on_fast_movement():
    f = OneEuroFilter(min_cutoff=1.0, beta=0.01)
    f.update(0, 0)
    value = 0.0
    for i in range(1, 16):  # Half a second at 30 fps.
        value = f.update(1000, i / 30)
    assert value > 900


def test_filter_ignores_a_repeated_timestamp():
    f = OneEuroFilter(min_cutoff=1.0, beta=0.01)
    f.update(10, 1.0)
    assert f.update(99, 1.0) == 10


def test_config_file_with_overrides(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('hand = "left"\nregion = [0.1, 0.1, 0.9, 0.9]\ncamera_index = 2\n')
    config = load_config(path, camera_index=3)
    assert config.hand == "left"
    assert config.region == (0.1, 0.1, 0.9, 0.9)
    assert config.camera_index == 3


def test_config_rejects_unknown_keys(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("pinch_entre = 0.3\n")
    with pytest.raises(ConfigError, match="pinch_entre"):
        load_config(path)


@pytest.mark.parametrize(
    "bad",
    [
        {"hand": "any"},
        {"cursor_hand": "both"},
        {"camera_rotation": 45},
        {"monitor": "laptop"},
        {"monitor": -1},
        {"region": (0.8, 0.2, 0.2, 0.8)},
        {"pinch_enter": 0.5, "pinch_exit": 0.4},
        {"stable_frames": 0},
    ],
)
def test_config_rejects_invalid_values(bad):
    with pytest.raises(ConfigError):
        Config(**bad)


def test_example_config_matches_the_defaults():
    from pathlib import Path

    example = Path(__file__).parent.parent / "config.example.toml"
    assert load_config(example) == Config()
