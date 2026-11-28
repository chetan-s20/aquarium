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


# ---- benchmark scoring (benchmark_tracker.py), offline

def test_benchmark_scores_perfect_and_swapped_tracks():
    from benchmark_tracker import score
    frames = 20
    gt = {f: [(1, 100 + f, 50, 40), (2, 300 - f, 50, 40)] for f in range(1, frames + 1)}
    perfect = {f: {"a": (100 + f, 52), "b": (300 - f, 48)} for f in range(1, frames + 1)}
    r = score(gt, perfect, frames)
    assert r["idf1"] == 1.0 and r["num_switches"] == 0 and r["recall"] == 1.0
    # halfway through, the tracker swaps which id is on which fish
    swapped = {f: (perfect[f] if f <= 10 else {"a": perfect[f]["b"], "b": perfect[f]["a"]}) for f in range(1, frames + 1)}
    r = score(gt, swapped, frames)
    assert r["num_switches"] == 2 and r["idf1"] < 0.6 and r["recall"] == 1.0


def test_dedupe_keeps_first_copy_and_drops_label_conflicts():
    from disease_data import dedupe

    labels = ["Healthy", "Healthy", "Parasitic", "Parasitic", "Healthy"]
    digests = ["a", "a", "b", "c", "c"]  # a: duplicate; c: filed under two classes
    assert dedupe(labels, digests) == [0, 2]


def test_yolo_labels_are_normalised_and_clipped_to_the_frame():
    from train_fish_detector import yolo_lines

    # one box inside a 200x100 frame, one hanging off the right edge, one fully outside
    lines = yolo_lines([(1, 50, 25, 20, 10), (2, 190, 0, 20, 10), (3, 300, 0, 5, 5)], w=200, h=100)
    assert lines == ["0 0.300000 0.300000 0.100000 0.100000", "0 0.975000 0.050000 0.050000 0.100000"]


def test_tracker_accepts_a_plugged_in_detector():
    from track_fish import FishTracker

    box = np.array([[40, 40, 60, 50]], np.float32)
    tracker = FishTracker(fps=10, max_fish=1, detector=lambda frame: (box, np.array([0.9], np.float32)))
    frame = np.zeros((100, 100, 3), np.uint8)
    seen = {}
    for _ in range(5):
        seen = tracker.update(frame)
    assert list(seen) == ["1"] and abs(seen["1"]["x"] - 0.5) < 0.01


def test_water_warning_labels_come_from_the_next_hours_and_skip_unsafe_now():
    from datetime import datetime, timedelta

    from train_water_model import make_samples

    t0 = datetime(2024, 1, 1)
    do = [7, 7, 7, 7, 7, 6, 4, 7, 7, 7, 7]  # dips below 5 mg/L at hour 6
    series = {t0 + timedelta(hours=i): {"do": v, "temp": 28.0, "ph": 7.5, "turbidity": 20.0} for i, v in enumerate(do)}
    X, y, times = make_samples(series, hours=3)
    labels = {t.hour: int(v) for t, v in zip(times, y)}
    assert labels == {3: 1, 4: 1, 5: 1, 7: 0}  # hour 6 (unsafe now) excluded; 0-2 lack history; 8+ lack future
    assert X[0][4] == 0 and X[2][4] == -1  # DO change over the last hour


def test_near_copies_share_a_group_even_flipped_or_resized():
    from disease_data import near_copy_groups

    rng = np.random.default_rng(0)
    a = cv2.GaussianBlur(rng.integers(0, 255, (120, 160), dtype=np.uint8), (15, 15), 0)
    b = cv2.GaussianBlur(rng.integers(0, 255, (120, 160), dtype=np.uint8), (15, 15), 0)
    a_copy = cv2.resize(cv2.flip(a, 1), (80, 60))  # same photo: mirrored and half size
    groups = near_copy_groups([a, b, a_copy])
    assert groups[0] == groups[2] != groups[1]


def test_disease_service_ranks_classes_and_rejects_non_images(tmp_path):
    import json
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer

    import torch

    from disease_service import Classifier, make_handler
    from train_disease_cnn import build_model

    classes = ["Healthy Fish", "Parasitic diseases", "White tail disease"]
    torch.save({"state_dict": build_model(3, pretrained=False).state_dict(), "classes": classes, "size": 224},
               tmp_path / "m.pt")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Classifier(tmp_path / "m.pt")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/predict"
    try:
        photo = cv2.imencode(".jpg", np.full((64, 64, 3), 120, np.uint8))[1].tobytes()
        body = json.loads(urllib.request.urlopen(urllib.request.Request(url, data=photo)).read())
        assert sorted(p["label"] for p in body["predictions"]) == sorted(classes)
        assert abs(sum(p["probability"] for p in body["predictions"]) - 1) < 0.01
        try:
            urllib.request.urlopen(urllib.request.Request(url, data=b"not a photo"))
            raise AssertionError("expected 422")
        except urllib.error.HTTPError as e:
            assert e.code == 422
    finally:
        server.shutdown()


def test_alarm_threshold_balances_missed_crashes_and_false_alarms():
    from train_water_model import best_threshold

    y = np.array([0, 0, 0, 1, 1])
    assert best_threshold(y, np.array([0.1, 0.2, 0.3, 0.8, 0.9])) == 0.8  # separates perfectly
    assert best_threshold(np.zeros(3, int), np.array([0.1, 0.2, 0.3])) == 0.5  # no crash to tune on
