"""OpenCV building blocks shared by training, prediction and the camera script."""
from pathlib import Path

import cv2
import numpy as np

IMAGE_SIZE = 128
FEATURE_VERSION = 1
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

_CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))


def hog(gray: np.ndarray, cell: int = 16, bins: int = 9) -> np.ndarray:
    """Histogram of oriented gradients, 2x2-cell normalised blocks.
    Hand-rolled because OpenCV 5 dropped cv2.HOGDescriptor from the main package."""
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=1)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=1)
    mag, ang = cv2.cartToPolar(gx, gy, angleInDegrees=True)
    b = ((ang % 180) / (180 / bins)).astype(int) % bins
    n = gray.shape[0] // cell
    rows, cols = np.indices(gray.shape) // cell
    hist = np.zeros((n, n, bins), np.float32)
    np.add.at(hist, (rows, cols, b), mag)
    blocks = np.stack([hist[i:i + 2, j:j + 2].ravel() for i in range(n - 1) for j in range(n - 1)])
    return (blocks / (np.linalg.norm(blocks, axis=1, keepdims=True) + 1e-6)).ravel()


def load_image(path: str | Path) -> np.ndarray:
    """cv2.imread can't open non-ASCII Windows paths; imdecode can."""
    img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"not a readable image: {path}")
    return img


def preprocess(img: np.ndarray) -> np.ndarray:
    """Resize and even out lighting (CLAHE on L channel): farm photos vary a lot in exposure."""
    img = cv2.resize(img, (IMAGE_SIZE, IMAGE_SIZE), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    lab[..., 0] = _CLAHE.apply(lab[..., 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def image_features(img: np.ndarray) -> np.ndarray:
    """Colour (red lesions, white spots, fungal cotton) + shape/texture (HOG) features."""
    img = preprocess(img)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hs = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256]).ravel()
    v = cv2.calcHist([hsv], [2], None, [8], [0, 256]).ravel()
    color = np.concatenate([hs, v]) / hsv[..., 0].size
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 160)
    extra = np.array([edges.mean() / 255, cv2.Laplacian(gray, cv2.CV_64F).var() / 1e4])
    return np.concatenate([color, hog(gray), extra]).astype(np.float32)


class ActivityMeter:
    """Fish movement from a fixed camera via background subtraction (MOG2).

    update(frame) -> (motion_pct, surface_pct)
      motion_pct  = % of frame pixels moving (overall activity)
      surface_pct = % of that motion in the top `surface_band` of the frame;
                    fish piping/gasping at the surface is a classic low-oxygen sign.
    """

    def __init__(self, surface_band: float = 0.2, history: int = 300, var_threshold: float = 25, width: int = 320):
        self.bg = cv2.createBackgroundSubtractorMOG2(history=history, varThreshold=var_threshold, detectShadows=False)
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        self.surface_band = surface_band
        self.width = width

    def update(self, frame: np.ndarray) -> tuple[float, float]:
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (self.width, max(1, round(h * self.width / w))))
        small = cv2.GaussianBlur(small, (5, 5), 0)  # ignore ripples / sensor noise
        mask = cv2.morphologyEx(self.bg.apply(small), cv2.MORPH_OPEN, self.kernel)
        moving = cv2.countNonZero(mask)
        top = cv2.countNonZero(mask[: max(1, int(mask.shape[0] * self.surface_band))])
        return 100.0 * moving / mask.size, (100.0 * top / moving if moving else 0.0)
