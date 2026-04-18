#!/bin/bash
# =============================================================================
# install.sh — Installation complète de SurValerte sur Raspberry Pi vierge
# Usage : sudo bash install.sh
# =============================================================================
set -e

# --- Couleurs -----------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
fail() { echo -e "${RED}[ERREUR]${NC} $1"; exit 1; }

# --- Vérifications préalables ------------------------------------------------
[ "$(id -u)" -eq 0 ] || fail "Ce script doit être lancé avec sudo : sudo bash install.sh"

INSTALL_USER="${SUDO_USER:-$(logname 2>/dev/null || echo pi)}"
HOME_DIR=$(eval echo "~$INSTALL_USER")
APP_DIR="$HOME_DIR/survalerte"
LOG="$HOME_DIR/survalerte_install.log"

echo "=============================================="
echo "  Installation SurValerte"
echo "  Utilisateur : $INSTALL_USER"
echo "  Dossier     : $APP_DIR"
echo "=============================================="
echo ""

# --- Attente réseau ----------------------------------------------------------
echo "Vérification de la connexion réseau..."
for i in $(seq 1 30); do
    if ping -c 1 -W 2 8.8.8.8 &>/dev/null; then
        ok "Réseau disponible"; break
    fi
    [ "$i" -eq 30 ] && fail "Pas de connexion internet après 60s. Vérifiez le réseau."
    sleep 2
done

# --- Question avahi ----------------------------------------------------------
echo ""
echo "=============================================="
echo -e "${YELLOW}  Accès à l'interface web${NC}"
echo "=============================================="
echo ""
echo "  Accès local : les deux options fonctionnent sur votre réseau"
echo "  domestique (wifi/ethernet)."
echo "  Accès depuis l'extérieur : possible via l'IP du Pi uniquement,"
echo "  en étant connecté au VPN de votre box (ex: VPN Freebox)."
echo "  Le nom survalerte.local ne fonctionne pas depuis l'extérieur."
echo ""
echo "  Option A — Accès par nom (ex: http://survalerte.local:5000)"
echo "    Nécessite l'installation d'avahi-daemon, un service de"
echo "    découverte réseau (protocole mDNS/Bonjour)."
echo -e "    ${YELLOW}Attention :${NC} ce service ouvre un port réseau supplémentaire"
echo "    sur le Pi. Risque faible sur un réseau domestique privé,"
echo "    mais à éviter si votre réseau est partagé ou peu sécurisé."
echo ""
echo "  Option B — Accès par adresse IP (ex: http://192.168.1.106:5000)"
echo "    Aucun service supplémentaire. Vous devrez connaître l'IP"
echo "    du Pi (visible dans l'interface de votre box)."
echo "    Accès réseau local uniquement, comme l'option A."
echo ""
read -r -p "  Installer avahi-daemon ? [o/N] : " AVAHI_CHOICE
echo ""

# --- Mise à jour système -----------------------------------------------------
echo "Mise à jour des paquets système..."
apt-get update -q >> "$LOG" 2>&1
apt-get install -y git python3 python3-pip python3-venv >> "$LOG" 2>&1
ok "Paquets système installés"

# --- Avahi (optionnel) -------------------------------------------------------
INSTALL_AVAHI=false
if [[ "$AVAHI_CHOICE" =~ ^[oO]$ ]]; then
    echo "Installation d'avahi-daemon..."
    apt-get install -y avahi-daemon >> "$LOG" 2>&1
    systemctl enable avahi-daemon >> "$LOG" 2>&1
    systemctl start avahi-daemon >> "$LOG" 2>&1
    ok "avahi-daemon installé — accès via http://$(hostname).local:5000"
    INSTALL_AVAHI=true
else
    warn "avahi-daemon non installé — accès par adresse IP uniquement"
fi

# --- Clonage du dépôt --------------------------------------------------------
echo ""
if [ -d "$APP_DIR" ]; then
    warn "Le dossier $APP_DIR existe déjà — mise à jour avec git pull"
    sudo -u "$INSTALL_USER" git -C "$APP_DIR" pull >> "$LOG" 2>&1
else
    echo "Clonage du dépôt GitHub..."
    sudo -u "$INSTALL_USER" git clone https://github.com/dcoldefy/RaspSurvAlerte.git "$APP_DIR" >> "$LOG" 2>&1
    ok "Dépôt cloné dans $APP_DIR"
fi

# --- Dépendances Python ------------------------------------------------------
echo ""
echo "Installation des dépendances Python..."
pip3 install --break-system-packages \
    flask requests FlightRadar24 reportlab python-docx >> "$LOG" 2>&1
ok "Dépendances Python installées"

# Mise à jour requirements.txt
cat > "$APP_DIR/requirements.txt" << 'EOF'
flask
requests
FlightRadar24
reportlab
python-docx
EOF

# --- Dossier de configuration ------------------------------------------------
mkdir -p "$HOME_DIR/.survalerte"
chown "$INSTALL_USER:$INSTALL_USER" "$HOME_DIR/.survalerte"
chown -R "$INSTALL_USER:$INSTALL_USER" "$APP_DIR"
ok "Dossier de configuration créé"

# --- Service systemd ---------------------------------------------------------
echo ""
echo "Configuration du service systemd..."
sed "s|/home/david|$HOME_DIR|g; s|User=david|User=$INSTALL_USER|g" \
    "$APP_DIR/survalerte.service" > /etc/systemd/system/survalerte.service
systemctl daemon-reload
systemctl enable survalerte >> "$LOG" 2>&1
systemctl start survalerte
ok "Service survalerte activé et démarré"

# --- Cron reboot quotidien ---------------------------------------------------
echo ""
echo "Configuration du reboot automatique quotidien à 3h..."
(crontab -l 2>/dev/null | grep -v "/sbin/reboot"; echo "0 3 * * * /sbin/reboot") | crontab -
ok "Reboot quotidien à 3h00 configuré"

# --- Résumé ------------------------------------------------------------------
IP=$(hostname -I | awk '{print $1}')
HOSTNAME=$(hostname)
echo ""
echo "=============================================="
echo -e "${GREEN}  Installation terminée avec succès !${NC}"
echo "=============================================="
echo ""
echo "  Interface web : http://$IP:5000"
if [ "$INSTALL_AVAHI" = true ]; then
echo "  Ou via nom    : http://$HOSTNAME.local:5000"
fi
echo ""
echo "  Logs service  : journalctl -u survalerte -f"
echo "  Redémarrer    : sudo systemctl restart survalerte"
echo ""
echo "  Prochaine étape : ouvrez l'interface et"
echo "  renseignez votre profil dans Réglages."
echo "=============================================="
