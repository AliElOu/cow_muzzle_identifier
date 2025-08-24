from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
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
from datetime import datetime
import sys

# Charger les variables d'environnement
load_dotenv(override=True)

# Configuration des logs
logging.basicConfig(level=logging.INFO)

# Debug: Vérifier les credentials
logging.info(f"🔑 Access Key: {os.getenv('AWS_ACCESS_KEY_ID')}")
logging.info(f"🌍 Region: {os.getenv('AWS_REGION')}")

# Vérification critique de S3 au démarrage
try:
    logging.info("🔍 Vérification de la connectivité S3...")
    
    # Vérifier les variables d'environnement AWS
    required_vars = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        raise Exception(f"Variables d'environnement manquantes: {', '.join(missing_vars)}")
    
    # Tester la connexion S3
    s3_manager = S3Manager()
    s3_manager.s3_client.head_bucket(Bucket=s3_manager.bucket_name)
    
    logging.info("✅ S3 accessible - démarrage de l'API")
    
except Exception as e:
    logging.critical(f"❌ ERREUR S3: {e}")
    logging.critical("🚫 L'API ne peut pas démarrer sans accès S3")
    sys.exit(1)

app = FastAPI()

# Configuration CORS
app.add_middleware( 
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Charger la base de données depuis S3 au démarrage
database = load_database()
logging.info(f"Base de données chargée avec {len(database.get('labels', []))} vaches")

# Initialisation du gestionnaire S3 (déjà vérifié au démarrage)
# s3_manager déjà initialisé lors de la vérification

# Créer les dossiers nécessaires pour la sauvegarde des prédictions
os.makedirs("prediction_results", exist_ok=True)

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



@app.post("/predict", 
          summary="Prédiction d'identité de vache",
          description="Prédit l'identité d'une vache à partir d'une seule image. L'image doit contenir un museau de vache visible.")
async def predict(image: UploadFile = File(..., description="Une seule image de vache (formats supportés: JPG, PNG, etc.)")):
    """Prédiction d'identité de vache à partir d'une seule image"""
    global database
    
    # Validation du type de fichier
    if not image.content_type.startswith('image/'):
        return JSONResponse(
            status_code=400,
            content={"error": "Le fichier doit être une image (jpg, png, etc.)"}
        )
    
    # Validation de la taille du fichier (max 10MB)
    max_size = 10 * 1024 * 1024  # 10MB
    if hasattr(image, 'size') and image.size > max_size:
        return JSONResponse(
            status_code=400,
            content={"error": "La taille de l'image ne doit pas dépasser 10MB"}
        )
    
    filename_only = os.path.basename(image.filename)
    temp_path = f"temp_{filename_only}"
    
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"error": f"Erreur lors de la lecture du fichier: {str(e)}"}
        )

    try:
        img_cv = cv2.imread(temp_path)
        if img_cv is None:
            return JSONResponse(
                status_code=400,
                content={"error": "Impossible de lire l'image. Format non supporté."}
            )
    finally:
        # Nettoyer le fichier temporaire même en cas d'erreur
        if os.path.exists(temp_path):
            os.remove(temp_path)

    # Détection du museau
    muzzle_img = detect_muzzle(img_cv)
    if muzzle_img is None:
        return JSONResponse({
            "prediction": "MUSEAU NON DÉTECTÉ",
            "score": 0,
            "muzzle_saved": False
        })
    
    # Générer un nom de fichier unique avec timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # microseconds tronquées
    muzzle_filename = f"prediction_{timestamp}_{filename_only}"
    muzzle_save_path = os.path.join("prediction_results", muzzle_filename)
    
    # Sauvegarder l'image du museau détecté
    cv2.imwrite(muzzle_save_path, muzzle_img)
    logging.info(f"Museau détecté sauvegardé: {muzzle_save_path}")
    
    img_tensor = load_and_preprocess_image(muzzle_img)
    label, score = predict_identity(img_tensor, database)

    # Gestion du cas où la base de données est vide
    if label == "BASE_VIDE":
        return JSONResponse({
            "prediction": "BASE DE DONNÉES VIDE",
            "score": 0.0,
            "muzzle_saved": True,
            "muzzle_save_path": muzzle_save_path,
            "original_filename": filename_only,
            "message": "Aucune vache enregistrée dans la base de données. Ajoutez des vaches avec /add-cow avant de faire des prédictions.",
            "total_cows_in_database": len(database.get("labels", []))
        })

    return JSONResponse({
        "prediction": label,
        "score": float(score),
        "muzzle_saved": True,
        "muzzle_save_path": muzzle_save_path,
        "original_filename": filename_only,
        "total_cows_in_database": len(database.get("labels", []))
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


@app.delete("/cow/{cow_id}")
async def delete_cow(cow_id: str):
    """Supprime une vache et toutes ses images de la base de données d'embeddings"""
    global database
    
    try:
        # Vérifier si la vache existe dans la base de données
        labels = database.get("labels", [])
        embeddings = database.get("embeddings", [])
        
        if cow_id not in labels:
            return JSONResponse(
                status_code=404,
                content={"error": f"Vache {cow_id} non trouvée dans la base de données"}
            )
        
        # Trouver l'index de la vache dans la base de données
        cow_index = labels.index(cow_id)
        
        # Créer une sauvegarde avant suppression
        backup_key = db_manager.backup_database()
        if not backup_key:
            logging.warning("Impossible de créer une sauvegarde avant suppression")
        
        # Supprimer la vache et son embedding de la base de données
        labels.pop(cow_index)
        embeddings.pop(cow_index)
        
        # Mettre à jour la base de données globale
        database["labels"] = labels
        database["embeddings"] = embeddings
        
        # Sauvegarder la base de données mise à jour
        save_success = save_database(database)
        
        # Supprimer le dossier local des images de museaux s'il existe
        muzzle_folder = f"muzzle_images/{cow_id}"
        muzzle_files_deleted = 0
        if os.path.exists(muzzle_folder):
            try:
                # Compter les fichiers avant suppression
                muzzle_files = [f for f in os.listdir(muzzle_folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                muzzle_files_deleted = len(muzzle_files)
                
                # Supprimer le dossier et son contenu
                shutil.rmtree(muzzle_folder)
                logging.info(f"Dossier de museaux {muzzle_folder} supprimé avec {muzzle_files_deleted} fichiers")
            except Exception as e:
                logging.warning(f"Impossible de supprimer le dossier {muzzle_folder}: {e}")
        
        return {
            "message": f"✅ Vache {cow_id} supprimée avec succès",
            "cow_id": cow_id,
            "embedding_removed": True,
            "database_saved_to_s3": save_success,
            "backup_created": backup_key is not None,
            "backup_location": f"s3://{db_manager.bucket_name}/{backup_key}" if backup_key else None,
            "muzzle_folder_deleted": os.path.exists(f"muzzle_images/{cow_id}") == False,
            "muzzle_files_deleted": muzzle_files_deleted,
            "remaining_cows_in_database": len(database.get("labels", []))
        }
        
    except Exception as e:
        logging.error(f"Erreur lors de la suppression de la vache {cow_id}: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Erreur lors de la suppression: {str(e)}",
                "cow_id": cow_id
            }
        )


@app.get("/cows")
async def list_all_cows():
    """Liste toutes les vaches présentes dans la base de données d'embeddings"""
    try:
        labels = database.get("labels", [])
        embeddings = database.get("embeddings", [])
        
        cows_info = []
        for i, cow_id in enumerate(labels):
            # Vérifier si le dossier de museaux existe localement
            muzzle_folder = f"muzzle_images/{cow_id}"
            muzzle_files_count = 0
            if os.path.exists(muzzle_folder):
                muzzle_files = [f for f in os.listdir(muzzle_folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                muzzle_files_count = len(muzzle_files)
            
            cows_info.append({
                "cow_id": cow_id,
                "index": i,
                "has_embedding": i < len(embeddings),
                "muzzle_folder_exists": os.path.exists(muzzle_folder),
                "muzzle_files_count": muzzle_files_count
            })
        
        return {
            "total_cows": len(labels),
            "cows": cows_info,
            "database_status": "loaded" if len(labels) > 0 else "empty"
        }
        
    except Exception as e:
        logging.error(f"Erreur lors de la récupération de la liste des vaches: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Erreur lors de la récupération: {str(e)}"}
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
