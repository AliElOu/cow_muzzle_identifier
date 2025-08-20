import json
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from tensorflow.keras.models import Model
from tensorflow.keras.models import load_model
from ultralytics import YOLO

model = load_model("utils/muzzle.keras")
embedding_model = Model(inputs=model.input, outputs=model.layers[-2].output)

# Charger ou initialiser la base
def load_database(path):
    with open(path, "r") as f:
        data = json.load(f)
    return {
        "labels": data["labels"],
        "embeddings": [np.array(emb) for emb in data["embeddings"]]
    }

def save_database(database, path="database.json"):
    db_copy = {
        "labels": database["labels"],
        "embeddings": [e.tolist() for e in database["embeddings"]],
    }
    with open(path, "w") as f:
        json.dump(db_copy, f)

# Extraire embedding
def get_embedding(img_tensor):
    return embedding_model.predict(img_tensor)[0]

# Identifier
def predict_identity(img_tensor, database, threshold=0.9):
    # Vérifier si la base de données contient des embeddings
    if not database.get("embeddings") or len(database["embeddings"]) == 0:
        return "BASE_VIDE", 0.0
    
    # Vérifier si la base de données contient des labels
    if not database.get("labels") or len(database["labels"]) == 0:
        return "BASE_VIDE", 0.0
    
    query_emb = get_embedding(img_tensor)
    sims = cosine_similarity([query_emb], database["embeddings"])[0]
    best_score = np.max(sims)
    best_index = np.argmax(sims)
    if best_score < threshold:
        return "INCONNUE", float(best_score)
    else:
        return database["labels"][best_index], float(best_score)
