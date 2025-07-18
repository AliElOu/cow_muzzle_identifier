from tensorflow.keras.preprocessing import image
import numpy as np
import cv2
from ultralytics import YOLO
from PIL import Image

yolo_model = YOLO("utils/best.pt")


def load_and_preprocess_image(img_np):
    img = Image.fromarray(cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB))
    img = img.resize((224, 224))
    x = image.img_to_array(img) / 255.0
    x = np.expand_dims(x, axis=0)
    return x

    
def detect_muzzle(image, conf=0.3):
    results = list(yolo_model(image, conf=conf))
    boxes = results[0].boxes
    if boxes is not None and len(boxes) > 0:
        box = boxes[0]
        x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
        cropped = image[y1:y2, x1:x2]
        return cropped
    return None