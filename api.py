"""
Appels aux APIs externes — geo.api.gouv.fr et hexdb.io.
"""
import urllib.parse
import requests

from config import GEO_API, GEO_API_CENTRE


def chercher_type_aeronef(icao24):
    """Retourne le code type OACI de l'aéronef via hexdb.io, ou None si inconnu."""
    try:
        r = requests.get(
            f"https://hexdb.io/api/v1/aircraft/{icao24.lower()}",
            timeout=3)
        if r.status_code == 200:
            return (r.json().get("Type") or "").strip().upper() or None
    except Exception:
        pass
    return None


def chercher_communes(code_postal):
    """Retourne la liste des noms de communes pour un code postal."""
    try:
        r = requests.get(GEO_API.format(cp=code_postal.strip()), timeout=5)
        if r.status_code == 200:
            return sorted([c["nom"] for c in r.json() if "nom" in c])
    except Exception:
        pass
    return []


def chercher_coordonnees_commune(code_postal, nom_commune, lat_defaut=48.9897, lon_defaut=2.0939):
    """Retourne (lat, lon) du centre de la commune, ou les coordonnées par défaut."""
    try:
        url = GEO_API_CENTRE.format(
            cp=code_postal.strip(),
            nom=urllib.parse.quote(nom_commune.strip()))
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            for c in r.json():
                if c.get("centre", {}).get("coordinates"):
                    lon_c, lat_c = c["centre"]["coordinates"]
                    return float(lat_c), float(lon_c)
    except Exception:
        pass
    return lat_defaut, lon_defaut
