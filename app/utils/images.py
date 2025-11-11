import numpy as np
from PIL import Image

def pil_to_rgb_numpy(img_pil: Image.Image) -> np.ndarray:
    if img_pil.mode != "RGB":
        img_pil = img_pil.convert("RGB")
    return np.array(img_pil)

def central_horizontal_crop(img_rgb: np.ndarray, width_frac: float = 0.8,
                            aspect: tuple[int,int] = (16,9),
                            max_height_frac: float = 0.8):
    """
    Recorta un rectángulo horizontal centrado.
    - width_frac: porcentaje del ancho original (0-1) -> por defecto 0.8 (80%)
    - aspect: (w,h) deseada (ej. 16:9)
    - max_height_frac: límite superior relativo para el alto (por si el alto resultante no cabe)

    Devuelve:
      (crop_img_rgb, (x1, y1, x2, y2)) en coordenadas de la imagen original
    """
    h, w = img_rgb.shape[:2]
    width_frac = float(max(0.1, min(1.0, width_frac)))
    max_height_frac = float(max(0.1, min(1.0, max_height_frac)))
    aw, ah = aspect

    # 1) Intento por ancho
    target_w = int(width_frac * w)
    target_h = int(round(target_w * (ah / aw)))

    # 2) Si no cabe por alto, recalcule por alto máximo permitido
    max_h = int(max_height_frac * h)
    if target_h > max_h:
        target_h = max_h
        target_w = int(round(target_h * (aw / ah)))

    # 3) Asegurar que no exceda límites de la imagen
    target_w = min(target_w, w)
    target_h = min(target_h, h)

    # 4) Asegurar forma horizontal (por si la imagen es muy "alta")
    if target_h >= target_w:
        # Fuerza horizontal reduciendo h
        target_h = max(1, int(round(target_w * (ah / aw))))
        if target_h > h:
            target_h = h
            target_w = max(1, int(round(target_h * (aw / ah))))

    # 5) Coordenadas centradas
    x1 = max(0, (w - target_w) // 2)
    y1 = max(0, (h - target_h) // 2)
    x2 = min(w, x1 + target_w)
    y2 = min(h, y1 + target_h)

    crop = img_rgb[y1:y2, x1:x2].copy()
    return crop, (x1, y1, x2, y2)