# 🐄 Cow Muzzle Identifier API - Docker

## 📋 Déploiement rapide sur EC2

### 1. Prérequis sur EC2
- Instance EC2 avec Ubuntu/Debian
- Ports 8000 ouverts dans le Security Group
- Clés AWS S3 configurées

### 2. Déploiement automatique
```bash
# Cloner le projet
git clone <votre-repo>
cd cow_api

# Configurer les variables AWS
cp .env.example .env
nano .env  # Ajoutez vos vraies clés AWS

# Lancer le script de déploiement
chmod +x deploy-ec2.sh
./deploy-ec2.sh
```

### 3. Configuration manuelle (alternative)
```bash
# 1. Construire l'image
docker build -t cow-api .

# 2. Lancer le conteneur
docker run -d \
  --name cow-api \
  -p 8000:8000 \
  -e AWS_ACCESS_KEY_ID=your_key \
  -e AWS_SECRET_ACCESS_KEY=your_secret \
  -e AWS_S3_BUCKET=your-bucket \
  -e AWS_REGION=us-east-1 \
  -v $(pwd)/muzzle_images:/app/muzzle_images \
  cow-api
```

### 4. Avec Docker Compose (recommandé)
```bash
# Configuration
cp .env.example .env
nano .env

# Lancement
docker-compose up -d

# Logs
docker-compose logs -f
```

### 5. URLs importantes
- API: `http://YOUR_EC2_IP:8000`
- Documentation: `http://YOUR_EC2_IP:8000/docs`
- Health check: `http://YOUR_EC2_IP:8000/health`

### 6. Commandes utiles
```bash
# Status
docker-compose ps

# Logs en temps réel
docker-compose logs -f cow-api

# Redémarrer
docker-compose restart

# Arrêter
docker-compose down

# Mise à jour du code
git pull
docker-compose build
docker-compose up -d
```

### 7. Configuration AWS requise
Dans le fichier `.env`:
```bash
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_S3_BUCKET=cow-muzzle-images
AWS_REGION=us-east-1
```
