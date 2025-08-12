# Configuration AWS S3 pour l'API Cow Muzzle Identifier

## Prérequis

1. **Compte AWS** avec accès à S3
2. **Bucket S3** créé pour stocker les images
3. **Utilisateur IAM** avec permissions S3

## Configuration

### 1. Créer un bucket S3

```bash
# Via AWS CLI (optionnel)
aws s3 mb s3://cow-muzzle-images --region us-east-1
```

Ou via la console AWS :
- Aller dans S3 → Créer un bucket
- Nom : `cow-muzzle-images` (ou autre nom de votre choix)
- Région : `us-east-1` (ou autre région)

### 2. Créer un utilisateur IAM

1. Aller dans IAM → Utilisateurs → Créer un utilisateur
2. Nom : `cow-api-s3-user`
3. Attacher la politique : `AmazonS3FullAccess` (ou créer une politique plus restrictive)

**Politique S3 minimale recommandée :**
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::cow-muzzle-images",
                "arn:aws:s3:::cow-muzzle-images/*"
            ]
        }
    ]
}
```

### 3. Générer les clés d'accès

1. Sélectionner l'utilisateur créé
2. Onglet "Informations d'identification de sécurité"
3. "Créer une clé d'accès"
4. Type : "Application s'exécutant en dehors d'AWS"
5. Sauvegarder les clés générées

### 4. Configurer les variables d'environnement

1. Copier le fichier `.env.example` vers `.env` :
```bash
cp .env.example .env
```

2. Éditer le fichier `.env` avec vos vraies valeurs :
```bash
AWS_ACCESS_KEY_ID=AKIA...votre_access_key
AWS_SECRET_ACCESS_KEY=votre_secret_key
AWS_S3_BUCKET=cow-muzzle-images
AWS_REGION=us-east-1
```

### 5. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 6. Démarrer l'API

```bash
cd cow_api
python main.py
```

## Utilisation

### Préparer les images d'une vache

1. **Uploader les images originales** dans le bucket S3 :
```bash
# Via AWS CLI
aws s3 cp image1.jpg s3://cow-muzzle-images/raw_images/vache_001/
aws s3 cp image2.jpg s3://cow-muzzle-images/raw_images/vache_001/
aws s3 cp image3.jpg s3://cow-muzzle-images/raw_images/vache_001/
```

Ou via la console AWS S3 :
- Aller dans votre bucket → `raw_images/`
- Créer un dossier avec l'ID de la vache (ex: `vache_001`)
- Uploader les images originales dans ce dossier

### Traiter une vache (seulement l'ID nécessaire)

```bash
curl -X POST "http://localhost:8000/add-cow" \
  -H "accept: application/json" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "cow_id=vache_001"
```

**Réponse :**
```json
{
    "message": "✅ Vache vache_001 ajoutée avec 2 images valides (museau détecté).",
    "images_found_in_s3": 3,
    "images_with_muzzle_detected": 2,
    "embeddings_extracted": 2
}
```

### Lister les images brutes d'une vache

```bash
curl -X GET "http://localhost:8000/cow/vache_001/raw-images"
```

### Vérifier l'état de l'API et S3

```bash
curl -X GET "http://localhost:8000/health"
```

## Structure des fichiers sur S3

```
cow-muzzle-images/
└── raw_images/              # Images originales des vaches (à uploader manuellement)
    ├── vache_001/
    │   ├── image1.jpg
    │   ├── image2.jpg
    │   └── image3.jpg
    ├── vache_002/
    │   ├── photo1.jpg
    │   └── photo2.jpg
    └── ...
```

## Workflow de traitement

1. **Préparer les images** : Uploader les images originales dans `raw_images/{cow_id}/`
2. **Traiter la vache** : Appeler `POST /add-cow` avec seulement l'ID
3. **L'API automatiquement** :
   - Cherche les images dans `raw_images/{cow_id}/`
   - Détecte les museaux dans chaque image
   - Extrait les embeddings des museaux détectés
   - Calcule la moyenne des embeddings et enregistre la vache
   - Supprime les fichiers temporaires locaux
   - **NE SAUVEGARDE PAS** les images de museaux coupées
│   │   ├── cropped_photo1.jpg
│   │   └── cropped_photo2.jpg
│   └── ...
```

## Dépannage

### Erreur de permissions AWS
- Vérifier que les clés d'accès sont correctes
- Vérifier que l'utilisateur IAM a les bonnes permissions S3
- Vérifier que le bucket existe et est accessible

### Erreur de bucket inexistant
- L'API essaiera de créer le bucket automatiquement
- Si ça échoue, créer le bucket manuellement dans la console AWS

### Variables d'environnement non trouvées
- Vérifier que le fichier `.env` existe dans le dossier `cow_api`
- Vérifier que toutes les variables requises sont définies
