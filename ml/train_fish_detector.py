"""Train a YOLO fish detector on 3D-ZeF20 (front camera), for the tracker benchmark.

    python ml/train_fish_detector.py [--epochs 6] [--per-seq 300] [--imgsz 640]
    python ml/benchmark_tracker.py --seq ZebraFish-02 --yolo ml/models/fish_yolo.pt   # then compare

Trains on ZebraFish-01, -03 and -04: --per-seq labelled frames spread evenly over each video, the
last 15% of each video held back for validation. ZebraFish-02, the benchmark sequence, is never seen,
so the benchmark compares YOLO with the OpenCV detector on unseen fish.
Starts from COCO-pretrained YOLO11n. Writes ml/models/fish_yolo.pt and ml/models/fish_yolo_report.json.

LICENCE: 3D-ZeF20 is CC BY-NC-SA 3.0. Weights trained on it are for internal testing only: never
commit or ship them. A farm detector needs boxes drawn on the farm's own video (docs/PLAN.md).
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent))
from benchmark_tracker import ROOT, fetch_frames, load_boxes  # noqa: E402

TRAIN_SEQS = ["ZebraFish-01", "ZebraFish-03", "ZebraFish-04"]
MODEL_DIR = Path(__file__).parent / "models"
DATASET = ROOT / "yolo"


def yolo_lines(rows, w: int, h: int) -> list[str]:
    """YOLO label lines (class cx cy w h, all 0..1) from (id, left, top, width, height) pixel boxes."""
    out = []
    for _, left, top, bw, bh in rows:
        x1, y1 = max(0.0, left), max(0.0, top)
        x2, y2 = min(float(w), left + bw), min(float(h), top + bh)
        if x2 > x1 and y2 > y1:
            out.append(f"0 {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}")
    return out


def build_dataset(per_seq: int) -> Path:
    for split in ("train", "val"):
        for kind in ("images", "labels"):
            shutil.rmtree(DATASET / kind / split, ignore_errors=True)
            (DATASET / kind / split).mkdir(parents=True)
    counts = {"train": 0, "val": 0}
    for seq in TRAIN_SEQS:
        boxes = load_boxes(seq)
        labelled = sorted(boxes)
        pick = labelled[:: max(1, len(labelled) // per_seq)][:per_seq]
        cut = labelled[int(len(labelled) * 0.85)]  # last 15% of the video: validation
        folder = fetch_frames(seq, pick)
        for f in pick:
            src = folder / f"{f:06d}.jpg"
            h, w = cv2.imread(str(src)).shape[:2]
            split = "val" if f >= cut else "train"
            name = f"{seq}_{f:06d}"
            shutil.copy(src, DATASET / "images" / split / f"{name}.jpg")
            (DATASET / "labels" / split / f"{name}.txt").write_text("\n".join(yolo_lines(boxes[f], w, h)) + "\n")
            counts[split] += 1
    yaml = DATASET / "fish.yaml"
    yaml.write_text(f"path: {DATASET}\ntrain: images/train\nval: images/val\nnames:\n  0: fish\n")
    print(f"dataset: {counts['train']} train / {counts['val']} validation frames from {', '.join(TRAIN_SEQS)}")
    return yaml


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--epochs", type=int, default=6, help="about 10 min each on a 4-core CPU")
    ap.add_argument("--per-seq", type=int, default=300, help="labelled frames per training video")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=8)
    args = ap.parse_args()

    from ultralytics import YOLO

    yaml = build_dataset(args.per_seq)
    os.chdir(ROOT)  # ultralytics downloads the pretrained weights into the working folder
    model = YOLO("yolo11n.pt")
    model.train(data=str(yaml), epochs=args.epochs, imgsz=args.imgsz, batch=args.batch, device="cpu",
                workers=2, project=str(ROOT / "runs"), name="fish", exist_ok=True, patience=8, plots=False, seed=0)
    best = ROOT / "runs" / "fish" / "weights" / "best.pt"
    metrics = YOLO(str(best)).val(data=str(yaml), imgsz=args.imgsz, batch=args.batch, device="cpu", plots=False)
    MODEL_DIR.mkdir(exist_ok=True)
    shutil.copy(best, MODEL_DIR / "fish_yolo.pt")
    report = {
        "base": "yolo11n (COCO)", "train_sequences": TRAIN_SEQS, "imgsz": args.imgsz, "epochs": args.epochs,
        "validation": {"precision": round(float(metrics.box.mp), 4), "recall": round(float(metrics.box.mr), 4),
                       "mAP50": round(float(metrics.box.map50), 4), "mAP50_95": round(float(metrics.box.map), 4)},
        "licence": "trained on 3D-ZeF20 (CC BY-NC-SA 3.0): internal testing only",
    }
    (MODEL_DIR / "fish_yolo_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
