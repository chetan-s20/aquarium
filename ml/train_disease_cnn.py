"""Fish-disease CNN: MobileNetV3 pretrained on ImageNet, fine-tuned on the Kaggle fish-disease images.

    python ml/train_disease_cnn.py [--epochs 12] [--data-dir path/with/Train_and_Test]

Uses the same cleaned images and the same 20% hold-out (test set) as the OpenCV models
(disease_data.py), so the scores compare. 10% of the fit set is a validation set that picks the best
epoch; the test set is scored once, at the end. OpenCV loads the images and evens out the lighting
(CLAHE). Writes ml/models/disease_cnn.pt and ml/models/disease_cnn_report.json. Runs on CPU.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import cv2
import torch
from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from torch import nn
from torchvision import models
from torchvision.transforms import v2 as T

sys.path.insert(0, str(Path(__file__).parent))
from disease_data import clean_split  # noqa: E402
from vision import load_image, preprocess  # noqa: E402

MODEL_DIR = Path(__file__).parent / "models"
SIZE = 224
NORMALIZE = [T.ToDtype(torch.float32, scale=True), T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])]
TRAIN_TF = T.Compose([T.RandomResizedCrop(SIZE, scale=(0.6, 1.0), antialias=True), T.RandomHorizontalFlip(),
                      T.ColorJitter(0.2, 0.2, 0.2), *NORMALIZE])
EVAL_TF = T.Compose([T.Resize(SIZE, antialias=True), *NORMALIZE])


def to_tensor(bgr) -> torch.Tensor:
    """uint8 3x256x256 tensor from an OpenCV image: CLAHE lighting correction, RGB."""
    img = cv2.cvtColor(preprocess(bgr, size=256), cv2.COLOR_BGR2RGB)
    return torch.from_numpy(img).permute(2, 0, 1).contiguous()


def load_rgb(path) -> torch.Tensor:
    return to_tensor(load_image(path))


def build_model(n_classes: int, pretrained: bool = True) -> nn.Module:
    weights = models.MobileNet_V3_Large_Weights.IMAGENET1K_V2 if pretrained else None
    model = models.mobilenet_v3_large(weights=weights)
    model.classifier[3] = nn.Linear(model.classifier[3].in_features, n_classes)
    return model


def batches(X, y, tf, size, shuffle, gen=None):
    order = torch.randperm(len(X), generator=gen) if shuffle else torch.arange(len(X))
    for s in range(0, len(X), size):
        idx = order[s:s + size]
        yield torch.stack([tf(X[i]) for i in idx]), y[idx]


@torch.no_grad()
def predict(model, X) -> torch.Tensor:
    model.eval()
    return torch.cat([model(xb).argmax(1) for xb, _ in batches(X, torch.zeros(len(X), dtype=torch.long), EVAL_TF, 64, False)])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", type=Path, help="folder containing Train/ and Test/")
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--batch", type=int, default=32)
    args = ap.parse_args()
    if args.data_dir is None:
        from download_dataset import dataset_root
        args.data_dir = dataset_root()
    torch.manual_seed(0)
    torch.set_num_threads(os.cpu_count() or 1)

    split = clean_split(args.data_dir)
    (fit_paths, fit_labels), (test_paths, test_labels) = split["fit"], split["hold"]
    classes = sorted(set(fit_labels))
    tr, va = train_test_split(range(len(fit_paths)), test_size=0.1, stratify=fit_labels, random_state=0)
    print(f"train {len(tr)}  validation {len(va)}  test {len(test_paths)}  classes {len(classes)}")

    print("Loading images ...")
    as_y = lambda labels: torch.tensor([classes.index(c) for c in labels])  # noqa: E731
    X_tr, y_tr = [load_rgb(fit_paths[i]) for i in tr], as_y([fit_labels[i] for i in tr])
    X_va, y_va = [load_rgb(fit_paths[i]) for i in va], as_y([fit_labels[i] for i in va])
    X_te, y_te = [load_rgb(p) for p in test_paths], as_y(test_labels)

    model = build_model(len(classes))
    opt = torch.optim.AdamW([
        {"params": model.features.parameters(), "lr": 2e-4},  # pretrained layers: small steps
        {"params": model.classifier.parameters(), "lr": 2e-3},
    ], weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.1)
    gen = torch.Generator().manual_seed(0)

    history, best_acc, best_state = [], -1.0, None
    for epoch in range(1, args.epochs + 1):
        t0, model_loss, n = time.time(), 0.0, 0
        model.train()
        for xb, yb in batches(X_tr, y_tr, TRAIN_TF, args.batch, True, gen):
            opt.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            opt.step()
            model_loss, n = model_loss + loss.item() * len(yb), n + len(yb)
        sched.step()
        val_acc = accuracy_score(y_va, predict(model, X_va))
        history.append({"epoch": epoch, "train_loss": round(model_loss / n, 4), "val_accuracy": round(val_acc, 4)})
        print(f"epoch {epoch:2d}  loss {model_loss / n:.3f}  val {val_acc:.3f}  ({time.time() - t0:.0f}s)", flush=True)
        if val_acc > best_acc:
            best_acc, best_state = val_acc, {k: v.clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    pred = predict(model, X_te)
    best_epoch = max(history, key=lambda h: h["val_accuracy"])["epoch"]
    report = {
        "arch": "mobilenet_v3_large (ImageNet IMAGENET1K_V2), fine-tuned",
        "classes": classes,
        "train_images": len(tr), "validation_images": len(va), "test_images": len(test_paths),
        "removed_duplicates_or_conflicts": split["removed"],
        "near_copy_images_kept_on_one_side": split["near_copy_images"],
        "best_epoch": best_epoch,
        "validation_accuracy": round(best_acc, 4),
        "holdout_accuracy": round(accuracy_score(y_te, pred), 4),
        "holdout_balanced_accuracy": round(balanced_accuracy_score(y_te, pred), 4),
        "chance_accuracy": round(1 / len(classes), 4),
        "per_class": classification_report(y_te, pred, target_names=classes, output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(y_te, pred).tolist(),
        "history": history,
    }
    print(classification_report(y_te, pred, target_names=classes, zero_division=0))
    print(f"test (hold-out) accuracy {report['holdout_accuracy']}  (chance {report['chance_accuracy']}, best epoch {best_epoch})")
    MODEL_DIR.mkdir(exist_ok=True)
    torch.save({"state_dict": best_state, "classes": classes, "size": SIZE}, MODEL_DIR / "disease_cnn.pt")
    (MODEL_DIR / "disease_cnn_report.json").write_text(json.dumps(report, indent=2))
    print(f"saved {MODEL_DIR / 'disease_cnn.pt'} and disease_cnn_report.json")


if __name__ == "__main__":
    main()
