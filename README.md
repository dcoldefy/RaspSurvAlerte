# RaspSurAlert

📖 **[Guide d'installation complet pour débutants](install/GUIDE_INSTALLATION.md)**

Surveillance aérienne locale sur Raspberry Pi — détecte les vols commerciaux survolant votre domicile et signale les infractions réglementaires (altitude trop basse, vol nocturne CDG).

## Fonctionnement

Un thread de fond interroge FlightRadar24 (ou OpenSky Network en option) toutes les 60 secondes sur une zone autour de vos coordonnées GPS. Chaque aéronef détecté est filtré (vols commerciaux uniquement) puis analysé :

| Infraction | Condition |
|------------|-----------|
| **ALTITUDE** | altitude < seuil légal configuré (défaut 1 150 m) |
| **NUIT** | vol hors plage horaire autorisée CDG |
| **DOUBLE** | les deux simultanément |

Les résultats sont affichés dans un dashboard web Bootstrap 5 accessible depuis n'importe quel appareil du réseau local.

## Installation (Raspberry Pi)

**Prérequis :** Raspberry Pi avec Raspberry Pi OS, accès internet.

```bash
# Cloner le dépôt
git clone https://github.com/dcoldefy/RaspSurvAlerte.git /home/david/survalerte
cd /home/david/survalerte

# Installation automatique (dépendances + service systemd)
sudo bash setup.sh
```

L'interface est ensuite accessible sur `http://<ip-du-pi>:5000`

## Lancement manuel (dev)

```bash
pip install flask requests FlightRadar24
python server.py
# → http://localhost:5000
```

## Configuration

Depuis l'interface web (`/reglages`) :

- **Profil** : nom, adresse, code postal — géolocalise automatiquement vos coordonnées GPS
- **Seuils** : altitude minimale légale, plage horaire nocturne, rayon de surveillance (km)
- **Source** : FlightRadar24 (défaut) ou OpenSky Network

La configuration est persistée dans `~/.survalerte/config.json`.

## Structure

```
server.py      — Application Flask + routes
scanner.py     — Thread de scan FR24/OpenSky (60 s)
filters.py     — Filtrage aéronefs + analyse infractions
database.py    — Couche SQLite (~/survalerte.db)
api.py         — Appels APIs externes (hexdb.io, geo.api.gouv.fr)
utils.py       — Helpers de formatage Jinja2
config.py      — Configuration (load/save JSON)
setup.sh       — Script d'installation Raspberry Pi
survalerte.service — Unit systemd
```

## APIs utilisées

- [FlightRadar24](https://www.flightradar24.com/) — flux ADS-B temps réel (source par défaut)
- [OpenSky Network](https://opensky-network.org/) — flux ADS-B alternatif (accès anonyme ou authentifié)
- [hexdb.io](https://hexdb.io/) — identification du type d'aéronef par code ICAO
- [geo.api.gouv.fr](https://geo.api.gouv.fr/) — géocodage commune → coordonnées GPS
