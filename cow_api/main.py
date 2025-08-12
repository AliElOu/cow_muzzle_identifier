from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse
import os
import shutil
import numpy as np
from utils.image_utils import load_and_preprocess_image, detect_muzzle
from utils.embeddings import get_embedding, predict_identity
from utils.s3_database import db_manager, load_database, save_database
from utils.aws_utils import S3Manager
import cv2
import logging
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration des logs
logging.basicConfig(level=logging.INFO)

app = FastAPI()

# Charger la base de données depuis S3 au démarrage
database = load_database()
logging.info(f"Base de données chargée avec {len(database.get('labels', []))} vaches")

# Initialisation du gestionnaire S3
s3_manager = S3Manager()

# Créer le bucket S3 si nécessaire au démarrage
try:
    s3_manager.create_bucket_if_not_exists()
except Exception as e:
    logging.error(f"Impossible d'initialiser S3: {e}")
    # L'application peut continuer, mais les uploads échoueront

@app.post("/add-cow")
async def add_cow(cow_id: str = Form(...)):
    global database
    embeddings = []

    try:
        # Récupérer la liste des images depuis S3 pour cette vache
        s3_images = s3_manager.list_cow_raw_images(cow_id)
        
        if not s3_images:
            return JSONResponse(status_code=404, content={
                "error": f"Aucune image trouvée pour la vache {cow_id} dans le bucket S3."
            })

        logging.info(f"Traitement de {len(s3_images)} images pour la vache {cow_id}")

        # Créer un dossier temporaire local pour le traitement
        temp_folder = f"temp_processing_{cow_id}"
        os.makedirs(temp_folder, exist_ok=True)
        
        # Créer un dossier local pour sauvegarder les museaux détectés
        muzzle_folder = f"muzzle_images/{cow_id}"
        os.makedirs(muzzle_folder, exist_ok=True)

        try:
            muzzle_count = 0
            for i, s3_image_key in enumerate(s3_images):
                # Télécharger l'image depuis S3
                local_image_path = os.path.join(temp_folder, f"image_{i}.jpg")
                success = s3_manager.download_image(s3_image_key, local_image_path)
                
                if not success:
                    logging.warning(f"Échec du téléchargement de {s3_image_key}")
                    continue

                # Charger et traiter l'image
                img_cv = cv2.imread(local_image_path)
                if img_cv is None:
                    logging.warning(f"Impossible de charger l'image {local_image_path}")
                    continue

                # Détecter le museau
                muzzle_img = detect_muzzle(img_cv, 0.1)
                if muzzle_img is None:
                    logging.info(f"Museau non détecté dans l'image {s3_image_key}")
                    continue

                # Sauvegarder l'image du museau localement
                muzzle_filename = f"muzzle_{cow_id}_{muzzle_count:03d}.jpg"
                muzzle_path = os.path.join(muzzle_folder, muzzle_filename)
                cv2.imwrite(muzzle_path, muzzle_img)
                muzzle_count += 1
                logging.info(f"Museau sauvegardé: {muzzle_path}")

                # Traitement pour les embeddings seulement (pas de sauvegarde)
                img_tensor = load_and_preprocess_image(muzzle_img)
                emb = get_embedding(img_tensor)
                embeddings.append(emb)
                logging.info(f"Embedding extrait de {s3_image_key}")

        finally:
            # Nettoyage du dossier temporaire local
            try:
                shutil.rmtree(temp_folder)
                logging.info(f"Dossier temporaire {temp_folder} supprimé")
            except Exception as e:
                logging.warning(f"Impossible de supprimer le dossier temporaire {temp_folder}: {e}")

        if len(embeddings) == 0:
            return JSONResponse(status_code=400, content={
                "error": "Aucune image valide (museau non détecté) trouvée.",
                "images_found": len(s3_images)
            })

        # Moyenne des embeddings et sauvegarde dans la base de données S3
        avg_embedding = np.mean(embeddings, axis=0)
        database["labels"].append(cow_id)
        database["embeddings"].append(avg_embedding.tolist())
        
        # Sauvegarder sur S3
        save_success = save_database(database)
        
        return {
            "message": f"✅ Vache {cow_id} ajoutée avec {len(embeddings)} images valides (museau détecté).",
            "images_found_in_s3": len(s3_images),
            "images_with_muzzle_detected": len(embeddings),
            "embeddings_extracted": len(embeddings),
            "muzzle_images_saved_to": muzzle_folder,
            "muzzle_files_count": muzzle_count,
            "database_saved_to_s3": save_success
        }

    except Exception as e:
        logging.error(f"Erreur lors du traitement de la vache {cow_id}: {e}")
        return JSONResponse(status_code=500, content={
            "error": f"Erreur lors du traitement: {str(e)}"
        })



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


@app.get("/cow/{cow_id}/raw-images")
async def get_cow_raw_images(cow_id: str):
    """Récupère la liste des images brutes d'une vache stockées sur S3"""
    try:
        raw_keys = s3_manager.list_cow_raw_images(cow_id)
        raw_urls = [f"https://{s3_manager.bucket_name}.s3.{s3_manager.region_name}.amazonaws.com/{key}" for key in raw_keys]
        return {
            "cow_id": cow_id,
            "raw_images_count": len(raw_urls),
            "s3_urls": raw_urls
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Erreur lors de la récupération des images brutes: {str(e)}"}
        )


@app.get("/cow/{cow_id}/muzzle-images")
async def get_cow_muzzle_images(cow_id: str):
    """Récupère la liste des images de museaux sauvegardées localement"""
    muzzle_folder = f"muzzle_images/{cow_id}"
    
    if not os.path.exists(muzzle_folder):
        return JSONResponse(
            status_code=404,
            content={"error": f"Aucune image de museau trouvée pour la vache {cow_id}"}
        )
    
    try:
        muzzle_files = [f for f in os.listdir(muzzle_folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        muzzle_files.sort()  # Tri par nom
        
        return {
            "cow_id": cow_id,
            "muzzle_images_count": len(muzzle_files),
            "muzzle_folder": muzzle_folder,
            "muzzle_files": muzzle_files
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Erreur lors de la lecture du dossier: {str(e)}"}
        )


@app.get("/health")
async def health_check():
    """Vérification de l'état de l'API et de la connectivité S3"""
    try:
        # Test de connectivité S3
        s3_manager.s3_client.head_bucket(Bucket=s3_manager.bucket_name)
        s3_status = "OK"
    except Exception as e:
        s3_status = f"ERROR: {str(e)}"
    
    # Informations sur la base de données
    db_info = db_manager.get_database_info()
    
    return {
        "api_status": "OK",
        "s3_status": s3_status,
        "bucket_name": s3_manager.bucket_name,
        "database_loaded": len(database.get("labels", [])) > 0,
        "database_info": db_info,
        "total_cows_in_database": len(database.get("labels", []))
    }


@app.get("/database/info")
async def get_database_info():
    """Informations détaillées sur la base de données"""
    db_info = db_manager.get_database_info()
    
    return {
        "total_cows": len(database.get("labels", [])),
        "cow_ids": database.get("labels", []),
        "storage_location": f"s3://{db_manager.bucket_name}/{db_manager.db_key}",
        "local_cache": db_manager.local_cache,
        "database_details": db_info
    }


@app.post("/database/backup")
async def create_database_backup():
    """Créer une sauvegarde manuelle de la base de données"""
    backup_key = db_manager.backup_database()
    if backup_key:
        return {
            "message": "Backup créé avec succès",
            "backup_location": f"s3://{db_manager.bucket_name}/{backup_key}",
            "backup_key": backup_key
        }
    else:
        return JSONResponse(
            status_code=500,
            content={"error": "Échec de la création du backup"}
        )


@app.post("/database/reload")
async def reload_database():
    """Recharge la base de données depuis S3"""
    global database
    try:
        database = load_database()
        return {
            "message": "Base de données rechargée depuis S3",
            "total_cows": len(database.get("labels", [])),
            "cow_ids": database.get("labels", [])
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Erreur lors du rechargement: {str(e)}"}
        )


if __name__ == "__main__":
        import uvicorn
        uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
