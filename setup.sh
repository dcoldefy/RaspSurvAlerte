#!/bin/bash
# setup.sh — Installation automatique de RaspSurAlert au premier démarrage
set -e

LOG="$HOME/survalerte_install.log"
APP="$HOME/survalerte"

echo "[$(date)] Début de l'installation RaspSurAlert" | tee -a "$LOG"

# Attendre la connexion réseau
echo "[$(date)] Attente connexion réseau..." | tee -a "$LOG"
for i in $(seq 1 30); do
  if ping -c 1 -W 2 8.8.8.8 &>/dev/null; then
    echo "[$(date)] Réseau OK" | tee -a "$LOG"
    break
  fi
  sleep 2
done

# Installation des dépendances
echo "[$(date)] Installation Flask et Requests..." | tee -a "$LOG"
apt-get update -q >> "$LOG" 2>&1
apt-get install -y python3-flask python3-requests >> "$LOG" 2>&1

# Répertoire de configuration
mkdir -p "$HOME/.survalerte"
chown "$USER:$USER" "$HOME/.survalerte"
chown -R "$USER:$USER" "$APP"

# Service systemd
echo "[$(date)] Activation du service RaspSurAlert..." | tee -a "$LOG"
sed "s|/home/david|$HOME|g; s|User=david|User=$USER|g" \
    "$APP/survalerte.service" > /etc/systemd/system/survalerte.service
systemctl daemon-reload
systemctl enable survalerte
systemctl start survalerte

echo "[$(date)] Installation terminée — http://survalerte.local:5000" | tee -a "$LOG"

# Ce service ne doit tourner qu'une seule fois
systemctl disable survalerte-setup.service
