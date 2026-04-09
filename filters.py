"""
Filtrage des aéronefs et analyse réglementaire des infractions.
"""
import re

# Types OACI des avions de transport commercial.
TRANSPORT_TYPES = {
    # Airbus narrow
    "A318", "A319", "A320", "A321",
    # Airbus wide
    "A330", "A332", "A333", "A338", "A339",
    "A340", "A342", "A343", "A345", "A346",
    "A350", "A359", "A35K",
    "A380", "A388",
    # A220 (ex C-Series Bombardier)
    "A220", "BCS1", "BCS3",
    # Boeing narrow (737 NG + MAX)
    "B737", "B732", "B733", "B734", "B735", "B736", "B738", "B739",
    "B37M", "B38M", "B39M",
    "737MAX", "737NG",
    # Boeing wide
    "B747", "B744", "B748",
    "B757", "B752", "B753",
    "B767", "B762", "B763", "B764",
    "B777", "777", "B772", "B773", "B77L", "B77W",
    "B778", "B779",
    "B787", "B788", "B789", "B78X",
    # Embraer commercial
    "E135", "E145", "E170", "E175", "E190", "E195", "E290", "E295",
    # Bombardier CRJ régional
    "CRJ2", "CRJ7", "CRJ9", "CRJX",
    # ATR
    "AT43", "AT45", "AT72", "AT75", "AT76",
    # Fokker
    "F70", "F100",
    # Dash 8
    "DH8A", "DH8B", "DH8C", "DH8D",
    # McDonnell Douglas
    "MD11", "MD81", "MD82", "MD83", "MD88", "MD90",
    # COMAC / Sukhoi
    "C919", "SU95", "SU9B",
}


def est_transport_commercial(type_code):
    """Retourne True si le code type OACI correspond à un avion de transport commercial.
    Tronque au premier espace pour gérer les variantes hexdb (ex. 'A320 214' → 'A320')."""
    code = (type_code or "").upper().split()[0] if type_code else ""
    return code in TRANSPORT_TYPES


# Format OACI : 3 lettres compagnie + 1-4 chiffres + 0-2 lettres suffixe
_CALLSIGN_RE = re.compile(r'^[A-Z]{3}[0-9]{1,4}[A-Z]{0,2}$')

# Catégories ADS-B à exclure : léger, petit, hélico, planeur, aérostat, ULM
_CAT_EXCLUES = {"A1", "A2", "A7", "B1", "B2", "B3", "B4"}


def est_avion_de_ligne(indicatif, vitesse_kmh, categorie=None):
    """
    Retourne True si l'aéronef est probablement un vol commercial.
    Couche 1 — indicatif : format OACI compagnie strict (3 lettres + chiffres).
    Couche 2 — vitesse   : > 150 km/h.
    Couche 3 — catégorie : exclut légers, hélicos, ULM, planeurs.
    """
    cs = (indicatif or "").strip().upper()
    if not cs or cs == "-":
        return False
    if not _CALLSIGN_RE.match(cs):
        return False
    if vitesse_kmh is not None and vitesse_kmh < 150:
        return False
    if categorie is not None and categorie in _CAT_EXCLUES:
        return False
    return True


def analyser_infraction(alt_m, heure_str, au_sol, cfg):
    """
    Retourne (code_infraction, message_detail) ou (None, "").
    Codes : "ALT", "NUIT", "ALT+NUIT".
    cfg : dict chargé depuis config.load().
    """
    if au_sol:
        return None, ""

    alt_min  = cfg["alt_min_legale"]
    nuit_deb = cfg["heure_nuit_deb"]
    nuit_fin = cfg["heure_nuit_fin"]

    infr_alt = (alt_m is not None and alt_m < alt_min)
    try:
        hh = int(heure_str.split(":")[0])
        infr_nuit = (hh >= nuit_deb or hh < nuit_fin)
    except Exception:
        infr_nuit = False

    if infr_alt and infr_nuit:
        return "ALT+NUIT", (
            f"DOUBLE INFRACTION : altitude {alt_m} m sous le minimum légal"
            f" de {alt_min} m ET vol à {heure_str} hors plage autorisée CDG"
            f" ({nuit_deb}h-{nuit_fin}h)")
    if infr_alt:
        return "ALT", (
            f"Altitude {alt_m} m inférieure au minimum légal"
            f" de {alt_min} m (arrêté 1957)")
    if infr_nuit:
        return "NUIT", (
            f"Vol à {heure_str} : restriction nocturne CDG"
            f" ({nuit_deb}h-{nuit_fin}h)")
    return None, ""
