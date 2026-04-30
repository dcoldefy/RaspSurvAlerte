# Guide d'installation de SurValerte sur Raspberry Pi

Ce guide vous accompagne pas à pas pour installer SurValerte sur un Raspberry Pi vierge, sans aucune connaissance technique préalable. À la fin, vous aurez une interface web accessible depuis n'importe quel appareil de votre réseau local.

**Durée estimée : 20 à 30 minutes**

---

## Ce dont vous avez besoin

**Matériel :**
- Un Raspberry Pi 3 ou 4
- Une carte microSD de 16 Go minimum (marque SanDisk ou Samsung recommandée)
- Une alimentation micro-USB (Pi 3) ou USB-C (Pi 4)
- Un câble Ethernet ou une connexion wifi

**Sur votre PC Windows :**
- Une connexion internet
- Un lecteur de carte SD (intégré ou USB)

---

## Étape 1 — Préparer la carte SD

### Télécharger et installer Raspberry Pi Imager

Rendez-vous sur **https://www.raspberrypi.com/software/** et cliquez sur **"Download for Windows"**. Lancez le fichier téléchargé et suivez l'installation (moins d'une minute).

Une fois installé, **lancez Raspberry Pi Imager** depuis le menu Démarrer.

---

### Configurer le flash

Dans Raspberry Pi Imager, effectuez les 3 sélections suivantes :

**1. "Choose Device"** → sélectionnez votre modèle de Pi (ex: **Raspberry Pi 3**)

**2. "Choose OS"** → **Raspberry Pi OS (other)** → **Raspberry Pi OS Lite (32-bit)**
> Le Lite n'a pas d'interface graphique — c'est parfait pour un serveur.
> Utilisez le 32-bit pour le Pi 3, le 64-bit pour le Pi 4 ou 5.

**3. "Choose Storage"** → sélectionnez votre carte SD

Cliquez sur **"Next"**, puis sur **"Edit Settings"** pour configurer l'installation.

---

### Paramètres avancés

**Onglet "General" :**

| Champ | Valeur |
|-------|--------|
| Hostname | `survalerte` _(suggéré)_ |
| Username | _(votre choix — notez-le)_ |
| Password | _(votre choix — notez-le)_ |
| Wifi SSID | _(nom de votre réseau wifi)_ |
| Wifi password | _(mot de passe wifi)_ |
| Timezone | `Europe/Paris` |

**Onglet "Services" :**
- Cochez **"Enable SSH"** → laissez sur **"Use password authentication"**

Cliquez sur **"Save"**, puis **"Yes"** deux fois pour lancer le flash.

> Si une fenêtre vous demande d'activer **Raspberry Pi Connect**, cliquez **"No"** — ce n'est pas nécessaire.

La durée est de **5 à 10 minutes** selon votre connexion internet.

---

## Étape 2 — Premier démarrage

Une fois le flash terminé, éjectez proprement la carte SD depuis Windows (clic droit sur le lecteur → **Éjecter**), insérez-la dans le Raspberry Pi et branchez l'alimentation.

Attendez **2 à 3 minutes** le temps que le Pi démarre et se connecte à votre wifi. Sur un Pi 3, le premier démarrage peut prendre plus de temps que les suivants — soyez patient.

> Si la connexion SSH échoue, attendez encore une minute et réessayez.

---

## Étape 3 — Connexion SSH

Ouvrez un terminal Windows (touche `Win` + `R`, tapez `cmd`, puis Entrée) et connectez-vous au Pi :

```
ssh votre-username@survalerte.local
```

> Si vous avez choisi un hostname différent de `survalerte`, remplacez `survalerte.local` par `votre-hostname.local`.

> Si vous obtenez `Are you sure you want to continue connecting?` → tapez `yes` puis Entrée.

Si `survalerte.local` ne répond pas, trouvez l'adresse IP du Pi dans l'interface de votre box (liste des appareils connectés) et utilisez :

```
ssh votre-username@192.168.1.XXX
```

---

## Étape 4 — Installation de SurValerte

Une fois connecté en SSH, lancez cette commande :

```bash
curl -sSL https://raw.githubusercontent.com/dcoldefy/RaspSurvAlerte/master/install/install.sh | sudo bash
```

Le script va vous poser une question :

```
Installer avahi-daemon ? [o/N]
```

- Répondez **`o`** pour accéder à l'interface via `http://survalerte.local:5000` (accès par nom)
- Répondez **`N`** pour accéder uniquement par adresse IP (ex: `http://192.168.1.XXX:5000`)

> Sur un réseau domestique privé, l'option `o` est recommandée pour plus de confort.

Le script effectue automatiquement :
- Mise à jour des paquets système
- Clonage du dépôt GitHub
- Installation des dépendances Python
- Configuration du service systemd (démarrage automatique au boot)
- Configuration d'un reboot quotidien à 15h

**Durée estimée : 5 à 10 minutes.**

À la fin, le script affiche l'adresse IP de votre Pi :

```
Interface web : http://192.168.1.XXX:5000
```

---

## Étape 5 — Configuration initiale

Ouvrez votre navigateur et accédez à l'interface :

```
http://survalerte.local:5000
```
ou par IP :
```
http://192.168.1.XXX:5000
```

> **Note Windows :** l'accès par nom (`survalerte.local`) ne fonctionne pas nativement sur Windows — utilisez l'adresse IP directe. Sur Mac, iPhone et Android, l'accès par nom fonctionne sans rien installer.

Cliquez sur **Réglages** et renseignez les informations suivantes :

**Profil :**
- Nom, prénom, adresse, code postal, ville

**Localisation :**
- Renseignez votre commune — les coordonnées GPS sont calculées automatiquement

**Seuils :**
- Altitude minimale légale (défaut : 1 200 m)
- Plage horaire nocturne (défaut : 00h30 – 05h00)
- Rayon de surveillance (défaut : 3 km)

Cliquez sur **Enregistrer**. Le scanner démarre automatiquement et interroge FlightRadar24 toutes les 60 secondes.

---

## Commandes utiles

> Ces commandes sont à taper dans un terminal SSH, une fois connecté au Pi (voir Étape 3).

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

> Pour quitter les logs en temps réel : appuyez sur `Ctrl + C`.

---

## Dépannage

| Problème | Solution |
|----------|----------|
| Interface inaccessible | `sudo systemctl restart survalerte` |
| Erreur scan FR24 | Vérifier la connexion internet : `curl https://google.com` |
| SSH timeout au premier démarrage | Attendre 2 minutes et réessayer, ou débrancher/rebrancher le Pi |
| `survalerte.local` inaccessible sur Windows | Utiliser l'adresse IP directe |
| SSH refuse la connexion | Trouver l'IP du Pi dans l'interface de votre box |
