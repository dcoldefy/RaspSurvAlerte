# Guide d'installation SurValerte sur Raspberry Pi vierge

## Prérequis matériel

- Raspberry Pi 3 ou 4 (recommandé)
- Carte microSD ≥ 8 Go
- Alimentation USB-C
- Connexion wifi ou câble Ethernet

---

## Étape 1 — Préparer la carte SD

1. Télécharger **Raspberry Pi Imager** : https://www.raspberrypi.com/software/
2. Choisir l'OS : **Raspberry Pi OS Lite (64-bit)** (sans interface graphique)
3. Avant de flasher, cliquer sur l'icône ⚙️ (paramètres avancés) et configurer :
   - **Nom d'hôte** : `survalerte`
   - **Activer SSH** : oui (avec mot de passe)
   - **Nom d'utilisateur** : `david` / mot de passe de votre choix
   - **Wifi** : SSID et mot de passe de votre box
   - **Fuseau horaire** : `Europe/Paris`
4. Flasher la carte SD et l'insérer dans le Pi

---

## Étape 2 — Premier démarrage

Brancher le Pi et attendre ~60 secondes. Puis depuis votre PC :

```bash
ssh david@survalerte.local
```

Si `survalerte.local` ne répond pas, trouver l'IP du Pi dans l'interface de votre box (liste des appareils connectés) et utiliser :

```bash
ssh david@<IP_DU_PI>
```

---

## Étape 3 — Installation automatique

Une fois connecté en SSH, lancer en une seule commande :

```bash
curl -sSL https://raw.githubusercontent.com/dcoldefy/RaspSurvAlerte/master/install/install.sh | sudo bash
```

Le script effectue automatiquement :
- Mise à jour des paquets système
- **Question sur avahi-daemon** (voir ci-dessous)
- Clonage du dépôt GitHub
- Installation des dépendances Python (Flask, FlightRadar24, ReportLab…)
- Configuration du service systemd (démarrage automatique)
- Configuration du reboot quotidien à 3h du matin

Durée estimée : 3 à 5 minutes.

### Avahi-daemon : accès par nom ou par IP ?

Pendant l'installation, le script vous posera la question suivante :

```
Installer avahi-daemon ? [o/N]
```

> **Dans les deux cas, l'accès est limité à votre réseau local** (wifi/ethernet de votre domicile). L'interface ne sera pas accessible depuis internet.

**Option A — Répondre `o` (accès par nom)** :
Installe `avahi-daemon`, un service de découverte réseau (protocole mDNS/Bonjour).
Vous pourrez accéder à l'interface via `http://survalerte.local:5000` sans connaître l'IP.
> **Attention :** ce service ouvre un port réseau supplémentaire sur le Pi. Le risque est faible sur un réseau domestique privé, mais à éviter si votre réseau wifi est partagé ou peu sécurisé.

**Option B — Répondre `N` (accès par IP, recommandé si sécurité prioritaire)** :
Aucun service supplémentaire n'est installé. Vous accéderez à l'interface en tapant directement l'adresse IP du Pi dans votre navigateur : `http://192.168.1.xxx:5000`. L'IP est visible dans l'interface de votre box (liste des appareils connectés). Accès réseau local uniquement, comme l'option A.

---

## Étape 4 — Accéder à l'interface

Une fois l'installation terminée, ouvrir dans un navigateur.

**Si avahi installé :**
```
http://survalerte.local:5000
```

**Sinon, avec l'IP directe :**
```
http://<IP_DU_PI>:5000
```

> L'IP exacte du Pi est affichée à la fin du script d'installation.

---

## Étape 5 — Configuration initiale

Dans l'interface web, aller dans **Réglages** et renseigner :

- **Profil** : nom, prénom, adresse (pour les lettres de plainte)
- **Localisation** : votre commune (géolocalisation automatique)
- **Seuils** : altitude minimale légale, plage horaire nocturne
- **Source de données** : FlightRadar24 (recommandé) ou OpenSky

---

## Étape 6 — Fixer l'IP du Pi (recommandé)

Pour que le Pi garde toujours la même IP même après un reboot de la box :

**Sur une Freebox :** Interface Freebox → Réseau local → Liste des appareils → Clic droit sur `survalerte` → **Configurer le bail DHCP** → cocher IP fixe.

---

## Commandes utiles (SSH)

```bash
# Voir les logs en temps réel
journalctl -u survalerte -f

# Redémarrer le service
sudo systemctl restart survalerte

# Vérifier l'état du service
sudo systemctl status survalerte

# Mettre à jour l'application
cd ~/survalerte && git pull && sudo systemctl restart survalerte
```

---

## Dépannage

| Problème | Solution |
|----------|----------|
| Interface inaccessible | `sudo systemctl restart survalerte` |
| Scanner bloqué (erreur réseau) | Vérifier la connexion internet du Pi : `curl https://google.com` |
| SSH timeout | Vérifier l'IP du Pi dans la box, ou débrancher/rebrancher le Pi |
| VPN actif non désiré | `sudo systemctl stop openvpn && sudo systemctl disable openvpn` |
