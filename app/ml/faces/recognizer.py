import json, os, numpy as np, joblib, face_recognition
from typing import List, Tuple

class FaceRecognizer:
    def __init__(self, model_path, scaler_path, labels_json, pca_path=None):
        self.loaded = False
        if all(os.path.exists(p) for p in [model_path, scaler_path, labels_json]):
            self.clf = joblib.load(model_path)
            self.scaler = joblib.load(scaler_path)
            self.pca = joblib.load(pca_path) if (pca_path and os.path.exists(pca_path)) else None
            with open(labels_json, "r", encoding="utf-8") as f:
                meta = json.load(f)
            self.labels = np.array(meta.get("classes_", meta.get("classes", [])))
            self.loaded = True

    def encodings(self, img_rgb, bboxes_trbl: List[List[int]]) -> np.ndarray:
        encs = face_recognition.face_encodings(
            img_rgb, known_face_locations=bboxes_trbl, num_jitters=1, model="small"
        )
        return np.vstack(encs).astype(np.float32) if encs else np.empty((0, 128), np.float32)

    def classify(self, embs: np.ndarray) -> List[Tuple[str, float]]:
        if not self.loaded or embs.size == 0:
            return []
        X = self.scaler.transform(embs)
        if self.pca is not None:
            X = self.pca.transform(X)
        proba = self.clf.predict_proba(X)
        ids = np.argmax(proba, axis=1)
        return [(str(self.labels[i]) if len(self.labels) else str(i), float(proba[j, i]))
                for j, i in enumerate(ids)]
