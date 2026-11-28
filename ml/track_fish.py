"""Track every fish in a tank video and send each fish's positions to the dashboard.

    # recorded video of the tank (side view), positions every 5 s, results to API + CSV
    python ml/track_fish.py --source tank.mp4 --start 2026-11-19T06:00:00Z --tank tank-a \\
        --api http://127.0.0.1:8000 --csv tracks.csv --background empty_tank.jpg --max-fish 12
    # live camera 0
    python ml/track_fish.py --source 0 --tank tank-a --api http://127.0.0.1:8000 --background empty_tank.jpg

Pipeline (OpenCV + Roboflow `trackers`):
  1. find fish: difference from a photo of the EMPTY tank (--background, recommended) or a slowly
     learned background (MOG2). Plain MOG2 slowly "forgets" a fish that stops moving, so a sick fish
     resting on the bottom would vanish; the empty-tank photo avoids that.
  2. link detections frame to frame with ByteTrack (trackers.ByteTrackTracker).
  3. re-link: when ByteTrack loses a fish (crossing, hiding) and starts a new track, give it back to
     the nearest recently-lost fish, so one fish keeps one id. Never more than --max-fish fish.
  4. every --sample-every seconds, record x/y (0..1 of the water area), body size and colour.

Limits: identity can still swap when two similar fish cross. For identity guaranteed across
a whole day use TRex or idtracker.ai and post their per-fish trajectories to the same endpoint
(POST /tanks/{tank}/fish-positions). See docs/PLAN.md.
"""
import argparse
import csv
import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
import supervision as sv
from trackers import ByteTrackTracker


def yolo_detector(weights: str, conf: float = 0.25):
    """Detector from trained YOLO weights: frame -> (xyxy boxes, confidences). See train_fish_detector.py."""
    from ultralytics import YOLO

    model = YOLO(weights)

    def detect(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        boxes = model.predict(frame, conf=conf, verbose=False)[0].boxes
        return boxes.xyxy.cpu().numpy().astype(np.float32), boxes.conf.cpu().numpy().astype(np.float32)

    return detect


class FishTracker:
    def __init__(self, fps: float, max_fish: int = 50, min_area: int = 40, background: np.ndarray | None = None,
                 relink_seconds: float = 30.0, relink_distance: float = 0.25, detector=None):
        """detector: optional frame -> (xyxy, confidence), e.g. yolo_detector(); replaces background subtraction."""
        self.detector = detector
        self.fps = fps
        self.max_fish = max_fish
        self.min_area = min_area
        self.background = None if background is None else cv2.GaussianBlur(background, (5, 5), 0)
        self.mog = cv2.createBackgroundSubtractorMOG2(history=2000, varThreshold=25, detectShadows=False)
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        self.bytetrack = ByteTrackTracker(frame_rate=fps, lost_track_buffer=int(fps * 2), track_activation_threshold=0.5,
                                          minimum_consecutive_frames=2)
        self.relink_frames = relink_seconds * fps
        self.relink_distance = relink_distance
        self.track_to_fish: dict[int, str] = {}
        self.last: dict[str, dict] = {}  # fish key -> {frame, x, y, size, color}
        self.frame_no = 0

    def _mask(self, frame: np.ndarray) -> np.ndarray:
        blur = cv2.GaussianBlur(frame, (5, 5), 0)
        if self.background is not None:
            diff = cv2.cvtColor(cv2.absdiff(blur, self.background), cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
        else:
            mask = self.mog.apply(blur, learningRate=0.0005)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel)

    def _fish_for(self, tid: int, x: float, y: float) -> str:
        if tid in self.track_to_fish:
            return self.track_to_fish[tid]
        active = set(self.track_to_fish.values())
        lost = [k for k, v in self.last.items() if k not in active or self.frame_no - v["frame"] > 1]
        recent = [k for k in lost if self.frame_no - self.last[k]["frame"] <= self.relink_frames]
        pool = recent if len(self.last) < self.max_fish else lost  # tank full: must be a known fish
        best = min(pool, key=lambda k: math.hypot(self.last[k]["x"] - x, self.last[k]["y"] - y), default=None)
        if best is not None and (len(self.last) >= self.max_fish or
                                 math.hypot(self.last[best]["x"] - x, self.last[best]["y"] - y) <= self.relink_distance):
            key = best
        else:
            key = str(len(self.last) + 1)
        for old_tid, k in list(self.track_to_fish.items()):  # a fish has one live track at a time
            if k == key:
                del self.track_to_fish[old_tid]
        self.track_to_fish[tid] = key
        return key

    def update(self, frame: np.ndarray) -> dict[str, dict]:
        """Returns the fish seen in this frame: key -> {x, y, size, color}."""
        self.frame_no += 1
        h, w = frame.shape[:2]
        if self.detector is not None:
            mask = None
            xyxy, conf = self.detector(frame)
        else:
            mask = self._mask(frame)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            boxes = [cv2.boundingRect(c) for c in contours if cv2.contourArea(c) >= self.min_area]
            xyxy = np.array([[x, y, x + bw, y + bh] for x, y, bw, bh in boxes], dtype=np.float32).reshape(-1, 4)
            conf = np.ones(len(xyxy), np.float32)
        if not len(xyxy):
            self.bytetrack.update(sv.Detections.empty())
            return {}
        dets = sv.Detections(xyxy=xyxy, confidence=conf, class_id=np.zeros(len(xyxy), int))
        tracked = self.bytetrack.update(dets)
        seen = {}
        for (x1, y1, x2, y2), tid in zip(tracked.xyxy, tracked.tracker_id):
            if tid is None or tid < 0:
                continue
            cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
            key = self._fish_for(int(tid), cx, cy)
            roi = (slice(int(y1), int(y2) + 1), slice(int(x1), int(x2) + 1))
            b, g, r = cv2.mean(frame[roi], mask=None if mask is None else mask[roi])[:3]
            info = {"x": round(float(cx), 4), "y": round(float(cy), 4), "size": round(float(max(x2 - x1, y2 - y1) / w), 4),
                    "color": f"#{int(r):02x}{int(g):02x}{int(b):02x}", "frame": self.frame_no}
            self.last[key] = info
            seen[key] = info
        return seen


def post(api: str, key: str, tank: str, positions: list[dict]) -> None:
    body = json.dumps({"positions": positions}).encode()
    req = urllib.request.Request(f"{api.rstrip('/')}/tanks/{tank}/fish-positions", body, method="POST",
                                 headers={"Content-Type": "application/json", "X-Device-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"  sent {len(positions)} positions: {r.read().decode()}")
    except urllib.error.HTTPError as e:
        print(f"  API rejected batch: {e.code} {e.read().decode()[:300]}", file=sys.stderr)
    except urllib.error.URLError as e:
        print(f"  API unreachable ({e.reason}); positions kept in CSV only", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="Track individual fish (OpenCV + ByteTrack)")
    ap.add_argument("--source", required=True, help="video file, or camera index like 0")
    ap.add_argument("--tank", required=True, help="tank id in the dashboard, e.g. tank-a")
    ap.add_argument("--roi", help="water area in the frame as x,y,w,h pixels (default: whole frame)")
    ap.add_argument("--background", type=Path, help="photo of the EMPTY tank from the same camera (recommended)")
    ap.add_argument("--max-fish", type=int, default=50, help="how many fish are in the tank")
    ap.add_argument("--min-area", type=int, default=40, help="smallest blob (pixels) that counts as a fish")
    ap.add_argument("--yolo", help="trained YOLO weights: detect fish with YOLO instead of background subtraction")
    ap.add_argument("--sample-every", type=float, default=5.0, help="seconds between stored positions")
    ap.add_argument("--start", help="ISO UTC time the video starts (files; default: file's modified time)")
    ap.add_argument("--csv", type=Path, help="also write positions here")
    ap.add_argument("--api", help="backend URL, e.g. http://127.0.0.1:8000")
    ap.add_argument("--device-key", default=os.environ.get("DEVICE_API_KEY", "dev-device-key-change-me"))
    args = ap.parse_args()

    live = args.source.isdigit()
    cap = cv2.VideoCapture(int(args.source) if live else args.source)
    if not cap.isOpened():
        sys.exit(f"cannot open video source {args.source}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    if live:
        start = datetime.now(timezone.utc)
    elif args.start:
        start = datetime.fromisoformat(args.start.replace("Z", "+00:00")).astimezone(timezone.utc)
    else:
        start = datetime.fromtimestamp(Path(args.source).stat().st_mtime, timezone.utc)
    rx, ry, rw, rh = map(int, args.roi.split(",")) if args.roi else (0, 0, 0, 0)

    def crop(img):
        return img[ry:ry + rh, rx:rx + rw] if args.roi else img

    background = None
    if args.background:
        background = cv2.imdecode(np.fromfile(str(args.background), np.uint8), cv2.IMREAD_COLOR)
        if background is None:
            sys.exit(f"cannot read background image {args.background}")
        background = crop(background)

    tracker = FishTracker(fps, args.max_fish, args.min_area, background,
                          detector=yolo_detector(args.yolo) if args.yolo else None)
    writer = None
    if args.csv:
        f = args.csv.open("w", newline="")
        writer = csv.writer(f)
        writer.writerow(["observed_at", "track_key", "x", "y", "size", "color_hex"])
    batch: list[dict] = []
    next_sample = 0.0
    frame_no = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = crop(frame)
        if background is not None and frame.shape != background.shape:
            sys.exit("background photo must be the same size as the video frames (after --roi)")
        seconds = frame_no / fps
        now = datetime.now(timezone.utc) if live else start + timedelta(seconds=seconds)
        frame_no += 1
        seen = tracker.update(frame)
        if seconds < next_sample:
            continue
        next_sample += args.sample_every
        for key, p in seen.items():
            row = {"track_key": key, "observed_at": now.isoformat(), "x": p["x"], "y": p["y"],
                   "size": p["size"] or None, "color_hex": p["color"]}
            batch.append(row)
            if writer:
                writer.writerow([row["observed_at"], key, p["x"], p["y"], p["size"], p["color"]])
        if args.api and len(batch) >= 500:
            post(args.api, args.device_key, args.tank, batch)
            batch = []
    if args.api and batch:
        post(args.api, args.device_key, args.tank, batch)
    cap.release()
    print(f"done: {frame_no} frames, {len(tracker.last)} fish identified")


if __name__ == "__main__":
    main()
