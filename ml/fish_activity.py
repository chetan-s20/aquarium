"""Measure fish behaviour from a tank camera with OpenCV and send it to the dashboard.

    # recorded video, results to CSV only
    python ml/fish_activity.py --source tank.mp4 --start 2026-11-19T06:00:00Z --csv activity.csv
    # live camera 0, posted to the API every minute as Pond A's camera sensors
    python ml/fish_activity.py --source 0 --tank pond-a --api http://127.0.0.1:8000

Per window (default 60 s) it reports:
  fish_activity    = average % of frame pixels moving
  surface_activity = % of the motion that is in the top 20% of the frame
Both go to POST /readings as sensors "<tank>-fish_activity" / "<tank>-surface_activity",
so they appear next to dissolved oxygen in the dashboard and CSV export.
Camera must be fixed (no pan/zoom); the first few seconds are used to learn the background.
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent))
from vision import ActivityMeter  # noqa: E402

WARMUP_SECONDS = 3


def post(api: str, key: str, sensor_id: str, value: float, at: datetime) -> None:
    body = json.dumps({"sensor_id": sensor_id, "value": round(value, 3), "observed_at": at.isoformat(), "source": "camera"})
    req = urllib.request.Request(f"{api.rstrip('/')}/readings", body.encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Device-Key": key})
    try:
        urllib.request.urlopen(req, timeout=10).close()
    except urllib.error.HTTPError as e:
        if e.code != 409:  # 409 = already stored, fine on re-runs
            print(f"  API rejected {sensor_id}: {e.code} {e.read().decode()[:200]}", file=sys.stderr)
    except urllib.error.URLError as e:
        print(f"  API unreachable ({e.reason}); value kept in CSV only", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="Fish activity from video (OpenCV)")
    ap.add_argument("--source", required=True, help="video file path, or camera index like 0")
    ap.add_argument("--window", type=int, default=60, help="seconds per reported value")
    ap.add_argument("--start", help="ISO UTC time the video starts (files only; default: file's modified time)")
    ap.add_argument("--csv", type=Path, help="also append results to this CSV")
    ap.add_argument("--tank", help="tank id; with --api, post readings for this tank")
    ap.add_argument("--api", help="backend URL, e.g. http://127.0.0.1:8000")
    ap.add_argument("--device-key", default=os.environ.get("DEVICE_API_KEY", "dev-device-key-change-me"))
    args = ap.parse_args()
    if args.api and not args.tank:
        ap.error("--api needs --tank")

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

    writer = None
    if args.csv:
        new = not args.csv.exists()
        f = args.csv.open("a", newline="")
        writer = csv.writer(f)
        if new:
            writer.writerow(["observed_at", "tank_id", "fish_activity", "surface_activity", "frames"])

    meter = ActivityMeter()
    frame_no, motion_sum, surface_weighted, n = 0, 0.0, 0.0, 0
    window_start = None
    t0 = time.monotonic()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        now = datetime.now(timezone.utc) if live else start + timedelta(seconds=frame_no / fps)
        elapsed = time.monotonic() - t0 if live else frame_no / fps
        frame_no += 1
        motion, surface = meter.update(frame)
        if elapsed < WARMUP_SECONDS:
            continue
        window_start = window_start or now
        motion_sum += motion
        surface_weighted += surface * motion  # weight by how much moved
        n += 1
        if (now - window_start).total_seconds() >= args.window:
            activity = motion_sum / n
            surface_share = surface_weighted / motion_sum if motion_sum else 0.0
            print(f"{now:%Y-%m-%d %H:%M:%S}Z  activity {activity:5.2f}%  surface {surface_share:5.1f}%  ({n} frames)")
            if writer:
                writer.writerow([now.isoformat(), args.tank or "", round(activity, 3), round(surface_share, 2), n])
            if args.api:
                post(args.api, args.device_key, f"{args.tank}-fish_activity", activity, now)
                post(args.api, args.device_key, f"{args.tank}-surface_activity", surface_share, now)
            window_start, motion_sum, surface_weighted, n = None, 0.0, 0.0, 0
    cap.release()


if __name__ == "__main__":
    main()
