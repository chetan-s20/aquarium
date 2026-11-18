# Optional camera / fish-disease ML module

This module is separate from sensor monitoring. It is NOT trained or validated in this repository state.

Dataset reference:
- Kaggle: "Freshwater Fish Disease Aquaculture in South Asia" (subirbiswas19)
- 7 classes, ~2,444 images (bacterial aeromoniasis, bacterial gill disease, bacterial red disease, fungal/saprolegniasis, healthy, parasitic, viral/white tail).
- Source: https://www.kaggle.com/datasets/subirbiswas19/freshwater-fish-disease-aquaculture-in-south-asia

Status:
- No dataset downloaded (Kaggle credentials not available in this environment).
- No model trained or evaluated here.
- torchvision/ultralytics are not installed; install manually if you want to train.

Expected local layout (user-provided, not committed):
data/ml/fish_disease/
  train/<class>/*.jpg
  val/<class>/*.jpg

Safety/quality notes:
- Image labels and capture conditions must be inspected before any claim of diagnostic performance.
- Model output is an assistive signal only, not a veterinary diagnosis.
- Camera timestamps must be aligned with sensor readings via observed_at (UTC) and device clock quality.
