"""Fish-disease images, cleaned and split the same way for every model, so their scores compare.

The Kaggle images are web-scraped, so the same photo appears more than once:
  - every official Test image is a byte-identical copy of a Train image, so the official split
    would report a fake 100%;
  - Train also holds resized, flipped, rotated or recompressed copies of the same photo. Split at
    random, ~11% of test images had a near-copy in the training set, which inflates test scores.
So: drop exact duplicates, group near-copies (perceptual hash, any flip or 90-degree turn), drop any
image or group filed under two classes, then hold out a stratified 20% of the GROUPS as the test set,
so no photo is on both sides.
"""
import hashlib
from pathlib import Path

import cv2
import numpy as np
from sklearn.model_selection import StratifiedGroupKFold

from vision import IMAGE_EXTS, load_image

NEAR_COPY_BITS = 4  # of 64 dHash bits; two photos this close are the same photo


def image_files(folder: Path) -> tuple[list[Path], list[str], list[str], list[str]]:
    """Readable images under folder/<class>/: paths, labels, md5 digests, and the unreadable paths."""
    paths, labels, digests, skipped = [], [], [], []
    for p in sorted(p for p in folder.rglob("*") if p.suffix.lower() in IMAGE_EXTS):
        try:
            load_image(p)
        except ValueError:
            skipped.append(str(p))
            continue
        paths.append(p)
        labels.append(p.parent.name)
        digests.append(hashlib.md5(p.read_bytes()).hexdigest())
    return paths, labels, digests, skipped


def dedupe(labels: list[str], digests: list[str]) -> list[int]:
    """Indices to keep: the first copy of each image, and none of an image filed under two classes."""
    classes_of: dict[str, set] = {}
    for d, label in zip(digests, labels):
        classes_of.setdefault(d, set()).add(label)
    keep, seen = [], set()
    for i, d in enumerate(digests):
        if d not in seen and len(classes_of[d]) == 1:
            keep.append(i)
        seen.add(d)
    return keep


def dhash(gray: np.ndarray) -> np.uint64:
    """64-bit difference hash: survives resizing and recompression."""
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).ravel()
    return np.uint64(int("".join("1" if b else "0" for b in bits), 2))


def near_copy_groups(grays: list[np.ndarray]) -> list[int]:
    """A group id per image; resized / flipped / rotated / recompressed copies share one."""
    variants = np.array([[dhash(cv2.rotate(f, cv2.ROTATE_90_CLOCKWISE) if turn else f)
                          for f in (g, cv2.flip(g, 1), cv2.flip(g, 0), cv2.flip(g, -1)) for turn in (0, 1)]
                         for g in grays], dtype=np.uint64)
    parent = list(range(len(grays)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for v in range(variants.shape[1]):  # variant v of image i against the original of image j
        close = np.bitwise_count(variants[:, v][:, None] ^ variants[None, :, 0]) <= NEAR_COPY_BITS
        for i, j in zip(*np.nonzero(close)):
            parent[root(int(i))] = root(int(j))
    return [root(i) for i in range(len(grays))]


def clean_split(root: Path) -> dict:
    """fit/hold paths and labels from root/Train, the Train digests, and what was removed."""
    paths, labels, digests, skipped = image_files(root / "Train")
    keep = dedupe(labels, digests)
    paths, labels = [paths[i] for i in keep], [labels[i] for i in keep]
    groups = near_copy_groups([cv2.cvtColor(load_image(p), cv2.COLOR_BGR2GRAY) for p in paths])
    classes_of: dict[int, set] = {}
    for g, label in zip(groups, labels):
        classes_of.setdefault(g, set()).add(label)
    ok = [i for i, g in enumerate(groups) if len(classes_of[g]) == 1]  # a photo filed under two diseases
    paths, labels, groups = [paths[i] for i in ok], [labels[i] for i in ok], [groups[i] for i in ok]
    fit, hold = next(StratifiedGroupKFold(5, shuffle=True, random_state=0).split(paths, labels, groups))
    sizes = np.bincount(np.unique(groups, return_inverse=True)[1])
    return {
        "fit": ([paths[i] for i in fit], [labels[i] for i in fit]),
        "hold": ([paths[i] for i in hold], [labels[i] for i in hold]),
        "train_digests": set(digests),
        "removed": len(digests) - len(paths),
        "near_copy_images": int(sizes[sizes > 1].sum()),
        "skipped": skipped,
    }
