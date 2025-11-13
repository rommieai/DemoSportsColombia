import numpy as np, torch
from PIL import Image
from transformers import CLIPProcessor, CLIPModel
import torch
from transformers import CLIPProcessor, CLIPModel


class GoalNoGoalClassifier:
    def __init__(self, model_path: str, labels_path: str, device: str = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.clip = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(self.device)
        self.proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        self.model = load_model(model_path)
        self.classes_ = np.load(labels_path, allow_pickle=True)

    def _clip_embedding(self, img_rgb: np.ndarray) -> np.ndarray:
        img = Image.fromarray(img_rgb)
        inputs = self.proc(images=img, return_tensors="pt").to(self.device)
        with torch.no_grad():
            emb = self.clip.get_image_features(**inputs)
        return emb[0].detach().cpu().numpy().astype(np.float32)

    def predict(self, img_rgb: np.ndarray, top_k=2):
        emb = self._clip_embedding(img_rgb).reshape(1, -1)
        proba = self.model.predict(emb, verbose=0)[0]
        idx = np.argsort(proba)[::-1][:top_k]
        return [{"event_class": str(self.classes_[i]),
                 "confidence": float(proba[i]),
                 "percentage": float(proba[i]*100)} for i in idx]
