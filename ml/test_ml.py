"""Self-checks for the OpenCV code on synthetic frames (no dataset needed).  python -m pytest ml"""
import sys
from pathlib import Path

import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent))
from vision import ActivityMeter, image_features  # noqa: E402


def _frames(y: int, moving: bool, n: int = 60):
    for i in range(n):
        f = np.full((240, 320, 3), 40, np.uint8)
        x = 40 + (i * 4 if moving else 0)
        cv2.circle(f, (x, y), 12, (200, 200, 200), -1)
        yield f


def _run(frames):
    meter = ActivityMeter()
    results = [meter.update(f) for f in frames]
    return results[-20:]  # after background is learned


def test_still_tank_has_no_activity():
    assert all(m < 0.1 for m, _ in _run(_frames(120, moving=False)))


def test_fish_at_surface_counts_as_surface_activity():
    tail = _run(_frames(20, moving=True))
    assert np.mean([m for m, _ in tail]) > 0.3
    assert np.mean([s for _, s in tail]) > 80


def test_fish_deep_in_tank_is_not_surface_activity():
    tail = _run(_frames(180, moving=True))
    assert np.mean([s for _, s in tail]) < 5


def test_image_features_fixed_length_for_any_image_size():
    a = image_features(np.random.randint(0, 255, (300, 500, 3), np.uint8))
    b = image_features(np.random.randint(0, 255, (90, 60, 3), np.uint8))
    assert a.shape == b.shape and np.isfinite(a).all()


# ---- individual fish tracking (track_fish.py)

def _swim(n_frames=240, crossing=False):
    """3 coloured 'fish' on a plain tank; returns frames and the empty-tank background."""
    bg = np.full((240, 320, 3), (90, 70, 40), np.uint8)
    colours = [(40, 120, 230), (200, 200, 200), (60, 180, 90)]
    frames = []
    for i in range(n_frames):
        f = bg.copy()
        paths = [(30 + i, 60), (290 - i, 60 if crossing else 120), (160, 30 + abs((i % 360) - 180))]
        for (x, y), c in zip(paths, colours):
            cv2.ellipse(f, (int(x), int(y)), (12, 6), 0, 0, 360, c, -1)
        frames.append(f)
    return frames, bg


def test_tracker_keeps_one_id_per_fish():
    from track_fish import FishTracker
    frames, bg = _swim()
    t = FishTracker(fps=10, max_fish=3, background=bg)
    prev: dict = {}
    for f in frames:
        seen = t.update(f)
        for k, p in seen.items():  # an id swap would show up as a sudden jump between consecutive frames
            if k in prev:
                assert abs(p["x"] - prev[k]["x"]) < 0.05 and abs(p["y"] - prev[k]["y"]) < 0.1, k
        prev = seen  # fish hidden behind another (merged blob) are skipped until they reappear
    assert set(t.last) == {"1", "2", "3"} and len(seen) == 3
    # the fish that swam left->right along y=60 ends on the right and keeps its orange colour
    orange = next(p for p in t.last.values() if abs(p["y"] - 0.25) < 0.03)
    assert orange["x"] > 0.7 and int(orange["color"][1:3], 16) > 0xC0


def test_tracker_never_invents_more_fish_than_tank_holds():
    from track_fish import FishTracker
    frames, bg = _swim(crossing=True)
    t = FishTracker(fps=10, max_fish=3, background=bg)
    for f in frames:
        t.update(f)
    assert len(t.last) == 3


def test_resting_fish_stays_visible_with_background_photo():
    from track_fish import FishTracker
    bg = np.full((120, 160, 3), 50, np.uint8)
    still = bg.copy()
    cv2.circle(still, (80, 100), 8, (220, 220, 220), -1)
    t = FishTracker(fps=10, max_fish=1, background=bg)
    for _ in range(300):  # 30 s motionless on the bottom
        seen = t.update(still)
    assert seen and seen["1"]["y"] > 0.75
