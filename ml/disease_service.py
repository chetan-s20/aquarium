"""Photo checker for the dashboard: a small HTTP service around the trained disease CNN.

    python ml/disease_service.py [--host 0.0.0.0] [--port 8100]   # needs ml/models/disease_cnn.pt

POST /predict  body = the photo's bytes  ->  {"predictions": [{"label", "probability"} x3], "model": ...}
GET  /health   ->  {"ok": true, "classes": 7}

The backend (POST /disease/check, operators only) calls this. Keep it on the internal network: it
has no login of its own. Output is a hint for staff to inspect a fish, not a diagnosis.
"""
import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent))
from train_disease_cnn import EVAL_TF, build_model, to_tensor  # noqa: E402

MODEL = Path(__file__).parent / "models" / "disease_cnn.pt"
MAX_BYTES = 10 * 1024 * 1024
MODEL_NAME = "MobileNetV3 CNN trained on web photos (not this farm's fish)"


class Classifier:
    def __init__(self, path: Path = MODEL):
        bundle = torch.load(path, map_location="cpu")
        self.classes = bundle["classes"]
        self.model = build_model(len(self.classes), pretrained=False)
        self.model.load_state_dict(bundle["state_dict"])
        self.model.eval()
        self.lock = threading.Lock()

    @torch.no_grad()
    def predict(self, data: bytes, top: int = 3) -> list[dict]:
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("not a readable photo")
        x = EVAL_TF(to_tensor(img)).unsqueeze(0)
        with self.lock:
            probs = torch.softmax(self.model(x), 1)[0]
        best = probs.topk(min(top, len(self.classes)))
        return [{"label": self.classes[i], "probability": round(float(p), 3)} for p, i in zip(best.values, best.indices)]


def make_handler(classifier: Classifier):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health":
                self._send(200, {"ok": True, "classes": len(classifier.classes)})
            else:
                self._send(404, {"detail": "not found"})

        def do_POST(self):
            if self.path != "/predict":
                return self._send(404, {"detail": "not found"})
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 < n <= MAX_BYTES:
                return self._send(413, {"detail": "send one photo of at most 10 MB"})
            try:
                preds = classifier.predict(self.rfile.read(n))
            except ValueError as e:
                return self._send(422, {"detail": str(e)})
            self._send(200, {"predictions": preds, "model": MODEL_NAME})

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8100)
    args = ap.parse_args()
    if not MODEL.exists():
        sys.exit(f"No model at {MODEL}. Train it first: python ml/train_disease_cnn.py")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(Classifier()))
    print(f"disease photo checker on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
