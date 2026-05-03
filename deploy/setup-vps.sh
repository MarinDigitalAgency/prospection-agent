#!/bin/bash
# Script de setup VPS — Ubuntu 24.04
# Exécuter en tant que root : bash /tmp/setup-vps.sh

set -e

echo "=== 1. Dépendances système ==="
apt-get update -qq
apt-get install -y \
    python3 python3-venv python3-pip \
    libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libgdk-pixbuf2.0-0 libffi-dev \
    shared-mime-info fonts-liberation \
    nginx

echo "=== 2. Répertoires ==="
mkdir -p /opt/prospection-agent/output/pdfs
mkdir -p /opt/prospection-agent/data/audits
mkdir -p /var/log/prospection-agent

echo "=== 3. Environnement Python ==="
cd /opt/prospection-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q gunicorn

echo "=== 4. Service systemd ==="
cp deploy/prospection-agent.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable prospection-agent
systemctl start prospection-agent

echo "=== 5. Nginx ==="
cp deploy/nginx-prospection.conf /etc/nginx/sites-available/prospection-agent
ln -sf /etc/nginx/sites-available/prospection-agent /etc/nginx/sites-enabled/prospection-agent
nginx -t && systemctl reload nginx

echo ""
echo "✅ Déploiement terminé !"
echo "   App     : http://audit.srv1380876.hstgr.cloud"
echo "   Logs    : journalctl -u prospection-agent -f"
echo "   Status  : systemctl status prospection-agent"
