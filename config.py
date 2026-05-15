"""
Configuration — constantes globales + config persistante JSON.
Aucune variable globale mutable : tout passe par load() / save().
"""
import json
import os

# Chemins fixes
APP_TITLE     = "SurvAlerte"
DB_FILE       = os.path.expanduser("~/survalerte.db")
CONFIG_PATH   = os.path.expanduser("~/.survalerte/config.json")
SCAN_INTERVAL = 60
DEDUP_WINDOW  = 600

# APIs externes
GEO_API        = "https://geo.api.gouv.fr/communes?codePostal={cp}&fields=nom&format=json"
GEO_API_CENTRE = "https://geo.api.gouv.fr/communes?codePostal={cp}&nom={nom}&fields=nom,centre&format=json"

# Valeurs par défaut (utilisées si config.json absent ou clé manquante)
DEFAULTS = {
    "alt_min_legale": 1150,
    "alt_max_scan": 8000,
    "heure_nuit_deb": 0.5,
    "heure_nuit_fin": 5,
    "rayon_km": 3,
    "lat": 48.9897,
    "lon": 2.0939,
    "opensky_user": "",
    "opensky_pass": "",
    "source": "flightradar24",
    "prefixes_exclus": ["JFA"],
    "admin_password_hash": "",
    "secret_key": "",
    "profil": {
        "nom": "",
        "prenom": "",
        "adresse": "",
        "code_postal": "",
        "ville": "",
    },
}


def load():
    """Charge la configuration JSON, complète avec les défauts si besoin."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            merged = dict(DEFAULTS)
            merged.update(data)
            merged["profil"] = dict(DEFAULTS["profil"])
            merged["profil"].update(data.get("profil", {}))
            return merged
        except Exception:
            pass
    return {**DEFAULTS, "profil": dict(DEFAULTS["profil"])}


def save(cfg):
    """Sauvegarde la configuration dans le fichier JSON."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass
