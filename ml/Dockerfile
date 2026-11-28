# Reproducible ML environment (OpenCV, scikit-learn, CPU PyTorch, YOLO). Build and run from the repo root:
#   docker build -t fishut-ml ml
#   docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work:z" fishut-ml python ml/train_disease_classifier.py
# Datasets and pretrained weights are cached under data/ (gitignored), so they download once.
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
# PyTorch first: the biggest download and the one that changes least, so requirement edits reuse it
RUN pip install --no-cache-dir --timeout 300 --retries 5 torch torchvision --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --timeout 300 --retries 5 -r /tmp/requirements.txt
ENV KAGGLEHUB_CACHE=/work/data/kagglehub TORCH_HOME=/work/data/torch YOLO_CONFIG_DIR=/work/data/ultralytics HOME=/tmp
WORKDIR /work
