from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse
import os
import shutil
import numpy as np
from utils.image_utils import load_and_preprocess_image, detect_muzzle
from utils.embeddings import load_database, save_database, get_embedding, predict_identity
import cv2

app = FastAPI()
db_path = "utils/embedding_database.json"
database = load_database(db_path)

@app.post("/add-cow")
async def add_cow(cow_id: str = Form(...), images: list[UploadFile] = File(...)):
    global database
    embeddings = []
    
    cow_folder = f"cow_data/{cow_id}"
    os.makedirs(cow_folder, exist_ok=True)

    for img_file in images:
        img_path = os.path.join(cow_folder, img_file.filename)
        with open(img_path, "wb") as buffer:
            shutil.copyfileobj(img_file.file, buffer)

        img_tensor = load_and_preprocess_image(img_path)
        emb = get_embedding(img_tensor)
        embeddings.append(emb)

    avg_embedding = np.mean(embeddings, axis=0)
    database["labels"].append(cow_id)
    database["embeddings"].append(avg_embedding)
    save_database(database, db_path)

    return {"message": f"✅ Vache {cow_id} ajoutée avec {len(images)} images."}


@app.post("/predict")
async def predict(image: UploadFile = File(...)):
    global database
    filename_only = os.path.basename(image.filename)
    temp_path = f"temp_{filename_only}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)

    img_cv = cv2.imread(temp_path)
    os.remove(temp_path)

    # Détection du museau
    muzzle_img = detect_muzzle(img_cv)
    if muzzle_img is None:
        return JSONResponse({
            "prediction": "MUSEAU NON DÉTECTÉ",
            "score": 0
        })
    img_tensor = load_and_preprocess_image(muzzle_img)
    label, score = predict_identity(img_tensor, database)

    return JSONResponse({
        "prediction": label,
        "score": float(score)
    })

