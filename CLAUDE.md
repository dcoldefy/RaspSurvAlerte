# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Démarrage rapide

```bash
pip install flask requests
python server.py
# Interface disponible sur http://localhost:5000
```

## Déploiement Raspberry Pi (systemd)

```bash
# Installation initiale (root)
bash setup.sh

# Gestion du service
systemctl status raspsuraler
systemctl restart raspsuraler
journalctl -u raspsuraler -f
```

## Architecture

Le projet est une application Flask mono-fichier `server.py` avec un thread de scan en arrière-plan. Voici comment les modules s'articulent :

```
server.py          — Flask app + routes + injection Jinja2 helpers
├── scanner.py     — Thread daemon Scanner (scan toutes les 60 s)
│   ├── api.py     — Appels HTTP : OpenSky (dans scanner), hexdb.io, geo.api.gouv.fr
│   ├── filters.py — Filtrage : est_avion_de_ligne(), est_transport_commercial(), analyser_infraction()
│   └── database.py— SQLite : save_passage(), update_passage(), get_active_flights()
├── config.py      — load()/save() JSON, constantes (DB_FILE, SCAN_INTERVAL, DEDUP_WINDOW)
└── utils.py       — Formatage Jinja2 (fmt_alt, fmt_val, fmt_pays, get_badge, get_css_class)
```

### Flux de données

1. `Scanner._loop()` appelle OpenSky toutes les `SCAN_INTERVAL=60s` sur la bounding box autour de `(lat, lon)` du config.
2. Chaque avion passe par deux filtres de `filters.py` : indicatif OACI + vitesse, puis type OACI via hexdb.io (mis en cache dans `scanner.state["aircraft_type_cache"]`).
3. `analyser_infraction()` compare l'altitude et l'heure aux seuils de config → codes `ALT`, `NUIT`, `ALT+NUIT`.
4. Les vols actifs sont dédupliqués en mémoire (`active_flights`) sur `DEDUP_WINDOW=600s` : un vol connu est mis à jour sauf s'il a déjà une infraction (then "frozen").
5. Flask sert les données via `/api/survols`, `/api/stats`, `/api/status` (polling JS toutes les 30 s dans `app.js`).

### Persistance

- **BDD** : SQLite sur `~/raspsuraler.db` — table unique `survols`.
- **Config** : JSON sur `~/.raspsuraler/config.json` — jamais de variables globales mutables, toujours `config.load()` / `config.save()`.

### Infractions détectées

| Code | Condition |
|------|-----------|
| `ALT` | altitude < `alt_min_legale` (défaut 1000 m) |
| `NUIT` | heure hors plage autorisée CDG (`heure_nuit_deb`–`heure_nuit_fin`) |
| `ALT+NUIT` | les deux simultanément |

### APIs externes

- **OpenSky Network** `opensky-network.org/api/states/all` — flux ADS-B (anonyme, limité)
- **hexdb.io** `hexdb.io/api/v1/aircraft/{icao24}` — type OACI de l'appareil
- **geo.api.gouv.fr** — géocodage commune → coordonnées GPS
