#!/bin/bash

# Script de déploiement pour EC2
# À exécuter sur votre instance EC2

echo "🚀 Déploiement de l'API Cow Muzzle Identifier sur EC2..."

# 1. Mise à jour du système
echo "📦 Mise à jour du système..."
sudo apt-get update && sudo apt-get upgrade -y

# 2. Installation de Docker
if ! command -v docker &> /dev/null; then
    echo "🐳 Installation de Docker..."
    sudo apt-get install -y docker.io
    sudo systemctl start docker
    sudo systemctl enable docker
    sudo usermod -aG docker $USER
fi

# 3. Installation de Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "🔧 Installation de Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# 4. Créer le fichier .env si nécessaire
if [ ! -f .env ]; then
    echo "⚙️ Création du fichier .env..."
    echo "Veuillez configurer vos variables AWS dans le fichier .env"
    cp .env.example .env
    echo "IMPORTANT: Éditez le fichier .env avec vos vraies clés AWS !"
    echo "nano .env"
fi

# 5. Construction et lancement
echo "🏗️ Construction de l'image Docker..."
docker-compose build

echo "🚀 Lancement de l'API..."
docker-compose up -d

echo "✅ Déploiement terminé !"
echo "🌐 L'API est accessible sur http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8000"
echo "📊 Health check: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8000/health"
echo ""
echo "📝 Commandes utiles:"
echo "  - Voir les logs: docker-compose logs -f"
echo "  - Arrêter l'API: docker-compose down"
echo "  - Redémarrer: docker-compose restart"
