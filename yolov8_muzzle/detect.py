from ultralytics import YOLO
import cv2
import os

model = YOLO("./yolov8_muzzle/best.pt")
images_dir = "./yolov8_muzzle/cow_images"


for i,image_name in enumerate(os.listdir(images_dir)):

    img_path = os.path.join(images_dir, image_name)
    image = cv2.imread(img_path)
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = model(img_path, conf=0.7)
    save_dir = "./yolov8_muzzle/results"
    os.makedirs(save_dir, exist_ok=True)
    boxes = results[0].boxes

    if boxes is not None and len(boxes) > 0:
        box = boxes[0]
        x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
        cropped = image[y1:y2, x1:x2]
        output_path = os.path.join(save_dir, f"cropped_{i}.jpg")
        cv2.imwrite(output_path, cropped)
        print(f"✅ Image sauvegardée dans : {output_path}")
    else:
        print("Aucune détéction est detectés.")