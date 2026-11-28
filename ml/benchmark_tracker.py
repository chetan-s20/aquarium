"""Score ml/track_fish.py on real fish with known identities (3D-ZeF20 zebrafish benchmark).

    python ml/benchmark_tracker.py                          # ZebraFish-02: 5 fish, 900 frames
    python ml/benchmark_tracker.py --seq ZebraFish-04 --frames 600

Uses the FRONT camera (a side view, like our tank cameras) and its hand-labelled boxes.
Downloads only that sequence's front-view frames (~0.5 GB) out of the 14 GB archive, using
HTTP range requests, into data/zef/ (git-ignored). Scoring uses py-motmetrics, the library the
MOTChallenge ZF3D kit is built on; we score in 2D image space, so no stereo calibration is needed.

Metrics (higher is better unless noted):
  IDF1        how well each fish keeps ONE id for the whole video (the number that matters for
              per-fish reports)
  ID switches times a fish's id jumped to another fish (lower is better)
  MOTA        overall: misses + false fish + id switches combined
  recall      share of labelled fish positions we found; precision: share of ours that were real

LICENCE: 3D-ZeF20 is CC BY-NC-SA 3.0 (non-commercial). Use it only to test the tracker
internally; never commit the data or ship anything trained on it.
"""
import argparse
import io
import json
import math
import sys
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import motmetrics as mm
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from track_fish import FishTracker  # noqa: E402

DATA_URL = "https://motchallenge.net/data/3DZeF20.zip"
LABELS_URL = "https://motchallenge.net/data/3DZeF20Lables.zip"
ROOT = Path(__file__).resolve().parents[1] / "data" / "zef"
FPS = 60


class HttpFile(io.RawIOBase):
    """Read-only, seekable view of a remote file via HTTP Range, so zipfile can pull single members."""

    def __init__(self, url: str):
        self.url, self.pos = url, 0
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60) as r:
            self.size = int(r.headers["Content-Length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def readinto(self, buf):
        n = min(len(buf), self.size - self.pos)
        if n <= 0:
            return 0
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{self.pos + n - 1}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        buf[: len(data)] = data
        self.pos += len(data)
        return len(data)


def remote_zip(url: str) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BufferedReader(HttpFile(url), buffer_size=1 << 20))


def fetch_frames(seq: str, frame_numbers) -> Path:
    """Download these front-camera frames (1-based numbers) of a sequence; returns their folder."""
    out = ROOT / seq / "imgF"
    out.mkdir(parents=True, exist_ok=True)
    wanted = [f"{i:06d}.jpg" for i in frame_numbers]
    missing = [w for w in wanted if not (out / w).exists()]
    if not missing:
        return out
    print(f"downloading {len(missing)} front-view frames of {seq} (only these, not the 14 GB archive)...")
    prefix = f"3DZeF20/train/{seq}/imgF/"

    def work(chunk):
        z = remote_zip(DATA_URL)  # one connection per worker; ZipFile isn't thread-safe
        for name in chunk:
            (out / name).write_bytes(z.read(prefix + name))
        return len(chunk)

    chunks = [missing[i::8] for i in range(8)]
    done = 0
    with ThreadPoolExecutor(8) as pool:
        for n in pool.map(work, chunks):
            done += n
            print(f"  {done}/{len(missing)}")
    return out


def load_boxes(seq: str) -> dict[int, list[tuple[int, float, float, float, float]]]:
    """frame -> [(fish id, left, top, width, height)]: the FRONT camera boxes, full-size pixels."""
    labels = ROOT / "labels.zip"
    if not labels.exists():
        ROOT.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(LABELS_URL, labels)
    text = zipfile.ZipFile(labels).read(f"3DZeF20Lables/train/{seq}/gt/gt.txt").decode()
    boxes: dict[int, list] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        v = [float(x) for x in line.split(",")]
        frame, fid, left, top, w, h = int(v[0]), int(v[1]), v[14], v[15], v[16], v[17]
        if w > 0 and h > 0:
            boxes.setdefault(frame, []).append((fid, left, top, w, h))
    return boxes


def load_gt(seq: str, n_frames: int) -> dict[int, list[tuple[int, float, float, float]]]:
    """frame -> [(fish id, box centre x, box centre y, match radius)] for the first n_frames."""
    # a detection counts as this fish if its centre is within half the box diagonal
    return {f: [(fid, l + w / 2, t + h / 2, 0.5 * math.hypot(w, h)) for fid, l, t, w, h in rows]
            for f, rows in load_boxes(seq).items() if f <= n_frames}


def median_background(frames: list[Path], scale: float) -> np.ndarray:
    """No empty-tank photo exists, so take the per-pixel median of frames spread over the video:
    fish keep moving, so each pixel is usually showing the tank behind them."""
    pick = frames[:: max(1, len(frames) // 25)]
    stack = [cv2.resize(cv2.imread(str(p)), None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) for p in pick]
    return np.median(np.stack(stack), axis=0).astype(np.uint8)


def score(gt: dict, hyp: dict, n_frames: int) -> dict:
    acc = mm.MOTAccumulator(auto_id=True)
    num: dict = {}  # motmetrics (with pandas 3) needs numeric ids; tracker keys are strings
    for f in range(1, n_frames + 1):
        g = gt.get(f, [])
        h = hyp.get(f, {})
        hk = list(h)
        for k in hk:
            num.setdefault(k, len(num) + 1)
        dist = np.full((len(g), len(hk)), np.nan)
        for i, (_, gx, gy, radius) in enumerate(g):
            for j, k in enumerate(hk):
                d = math.hypot(gx - h[k][0], gy - h[k][1])
                if d <= radius:
                    dist[i, j] = d
        acc.update([x[0] for x in g], [num[k] for k in hk], dist)
    names = ["idf1", "mota", "num_switches", "recall", "precision", "num_unique_objects",
             "mostly_tracked", "num_false_positives", "num_misses"]
    summary = mm.metrics.create().compute(acc, metrics=names, name="tracker")
    return {k: (round(float(summary[k].iloc[0]), 4) if isinstance(summary[k].iloc[0], float) else int(summary[k].iloc[0]))
            for k in names}


def run(seq: str, n_frames: int, scale: float, min_area: int, yolo: str | None = None) -> dict:
    gt = load_gt(seq, n_frames)
    n_frames = min(n_frames, max(gt))
    folder = fetch_frames(seq, range(1, n_frames + 1))
    frames = [folder / f"{i:06d}.jpg" for i in range(1, n_frames + 1)]
    n_fish = len({fid for rows in gt.values() for fid, *_ in rows})
    if yolo:
        from track_fish import yolo_detector
        tracker = FishTracker(fps=FPS, max_fish=n_fish, detector=yolo_detector(yolo))
    else:
        tracker = FishTracker(fps=FPS, max_fish=n_fish, min_area=min_area, background=median_background(frames, scale))
    hyp: dict[int, dict] = {}
    H, W = cv2.imread(str(frames[0])).shape[:2]
    for i, p in enumerate(frames, start=1):
        img = cv2.resize(cv2.imread(str(p)), None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        seen = tracker.update(img)
        hyp[i] = {k: (v["x"] * W, v["y"] * H) for k, v in seen.items()}  # back to full-size pixels
    result = {"sequence": seq, "detector": f"yolo:{Path(yolo).name}" if yolo else "opencv-background",
              "frames": n_frames, "fish": n_fish, "scale": scale, "min_area": min_area, **score(gt, hyp, n_frames)}
    return result


def main():
    ap = argparse.ArgumentParser(description="Benchmark track_fish.py on 3D-ZeF20 (front camera)")
    ap.add_argument("--seq", default="ZebraFish-02", choices=[f"ZebraFish-0{i}" for i in range(1, 5)],
                    help="training sequence (these have labels)")
    ap.add_argument("--frames", type=int, default=900, help="how many frames from the start (60 fps)")
    ap.add_argument("--scale", type=float, default=0.5, help="resize frames before tracking (speed)")
    ap.add_argument("--min-area", type=int, default=300, help="smallest blob (pixels, after scaling) that counts as a fish")
    ap.add_argument("--yolo", help="trained YOLO weights (train_fish_detector.py) instead of background subtraction")
    args = ap.parse_args()
    r = run(args.seq, args.frames, args.scale, args.min_area, args.yolo)
    print(json.dumps(r, indent=2))
    (ROOT / f"report-{args.seq}{'-yolo' if args.yolo else ''}.json").write_text(json.dumps(r, indent=2))
    print(f"\nIDF1 {r['idf1']:.0%} (keeping one id per fish) | {r['num_switches']} id switches | "
          f"found {r['recall']:.0%} of fish positions | {r['precision']:.0%} of detections were real fish")


if __name__ == "__main__":
    main()
