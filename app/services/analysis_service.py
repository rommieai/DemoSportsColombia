from __future__ import annotations

from typing import List
import mediapipe as mp
import numpy as np
from app.ml.faces.recognizer import FaceRecognizer
from app.ml.classifiers.goal_clip_keras import GoalNoGoalClassifier
from app.ml.detectors.jerseys import JerseyDetector
from app.schemas.io import FacePrediction, EventPrediction, JerseyDetection, CompleteResponse

mp_face_detection = mp.solutions.face_detection

class AnalysisService:
    def __init__(self, face_rec: FaceRecognizer,
                 goal_clf: GoalNoGoalClassifier,
                 jersey_det: JerseyDetector):
        self.face_rec = face_rec
        self.goal_clf = goal_clf
        self.jersey_det = jersey_det

    def analyze(self, img_pil) -> CompleteResponse:
        from app.utils.images import pil_to_rgb_numpy
        img_rgb = pil_to_rgb_numpy(img_pil)

        # 1) Detección de caras (MediaPipe)
        faces_out: List[FacePrediction] = []
        bboxes_trbl, det_scores = [], []
        
        with mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5) as fd:
            res = fd.process(img_rgb)
            
        if res and res.detections:
            h, w = img_rgb.shape[:2]
            for det in res.detections:
                rb = det.location_data.relative_bounding_box
                x, y = int(rb.xmin*w), int(rb.ymin*h)
                ww, hh = int(rb.width*w), int(rb.height*h)
                x, y = max(0,x), max(0,y)
                x2, y2 = min(w-1, x+ww), min(h-1, y+hh)
                top, right, bottom, left = y, x2, y2, x
                bboxes_trbl.append([top,right,bottom,left])
                det_scores.append(float(det.score[0]) if det.score else 0.0)

        # 1.2) Embeddings + clasificación
        labels_scores = []
        if bboxes_trbl:
            embs = self.face_rec.encodings(img_rgb, bboxes_trbl)
            labels_scores = self.face_rec.classify(embs)

        for i, trbl in enumerate(bboxes_trbl):
            if i < len(labels_scores):
                lbl, s = labels_scores[i]
                faces_out.append(FacePrediction(bbox=list(map(int, trbl)), label=str(lbl), score=float(s)))
            else:
                faces_out.append(FacePrediction(bbox=list(map(int, trbl)), label="unknown",
                                                score=float(det_scores[i]) if i < len(det_scores) else 0.0))

        # 2) Goal/NoGoal
        preds = self.goal_clf.predict(img_rgb, top_k=2)
        if preds:
            event_predictions = [EventPrediction(**p) for p in preds]
            top_event = event_predictions[0]
        else:
            event_predictions = []
            top_event = EventPrediction(event_class="Unknown", confidence=0.0, percentage=0.0)

        # 3) Camisetas - CORREGIDO: ahora sí define las variables
        jerseys_raw = self.jersey_det.detect(img_rgb)
        jerseys = [JerseyDetection(**j) if isinstance(j, dict) else j for j in jerseys_raw]
        a_cnt = sum(1 for j in jerseys if j.team == "Argentina")
        f_cnt = sum(1 for j in jerseys if j.team == "France")

        return CompleteResponse(
            num_faces=len(faces_out),
            faces=faces_out,
            event_predictions=event_predictions,
            top_event=top_event,
            jerseys=jerseys,
            argentina_count=a_cnt,
            france_count=f_cnt,
            image_processed=True,
            total_detections=len(faces_out) + len(jerseys),
        )