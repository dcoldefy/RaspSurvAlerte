"""
Fonctions utilitaires — formatage, distance GPS, classification infraction.
"""
import math


def distance_km(lat1, lon1, lat2, lon2):
    """Distance en km entre deux points GPS (formule de Haversine)."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def fmt_dist(d):
    return f"{d:.1f} km" if d is not None else "—"


def fmt_heure(h):
    """Formate un float heure (ex: 0.5 → '00h30', 22.0 → '22h00')."""
    return f"{int(h):02d}h{'30' if h % 1 else '00'}"


def fmt_alt(alt):
    return f"{alt:,} m".replace(",", "\u202f") if alt is not None else "-"


def fmt_val(v, suffix=""):
    return f"{v}{suffix}" if v is not None else "-"


FLAG_MAP = {
    "France": "FR", "Germany": "DE", "United Kingdom": "GB",
    "Netherlands": "NL", "Spain": "ES", "United States": "US",
    "Italy": "IT", "Belgium": "BE", "Switzerland": "CH",
    "Portugal": "PT", "Ireland": "IE", "Turkey": "TR",
    "Norway": "NO", "Sweden": "SE", "Denmark": "DK",
    "Poland": "PL", "Austria": "AT", "Luxembourg": "LU", "Morocco": "MA",
}


def fmt_pays(c):
    code = FLAG_MAP.get(c, "")
    return f"[{code}] {c}" if code else (c or "-")


def get_code(msg):
    """Extrait le code d'infraction depuis le message texte."""
    if not msg:
        return ""
    if "DOUBLE" in msg:
        return "ALT+NUIT"
    if "minimum légal" in msg:
        return "ALT"
    if "restriction" in msg:
        return "NUIT"
    return ""


def get_css_class(code):
    """Retourne la classe CSS pour une ligne du tableau."""
    return {
        "ALT+NUIT": "row-double",
        "ALT":      "row-alt",
        "NUIT":     "row-nuit",
    }.get(code, "")


def get_badge(code):
    """Retourne le HTML du badge d'infraction."""
    badges = {
        "ALT+NUIT": '<span class="badge bg-danger">DOUBLE</span>',
        "ALT":      '<span class="badge bg-warning text-dark">ALTITUDE</span>',
        "NUIT":     '<span class="badge bg-info text-dark">NUIT</span>',
    }
    return badges.get(code, "")


def get_seuil_display(code, msg):
    """Extrait un résumé court des seuils depuis le message d'infraction."""
    import re
    if not code or not msg:
        return ""
    parts = []
    if "ALT" in code:
        m = re.search(r'minimum légal de (\d+) m', msg)
        if m:
            parts.append(f"< {m.group(1)} m")
    if "NUIT" in code:
        m = re.search(r'\((\d+h\d+)-(\d+h\d+)\)', msg)
        if m:
            parts.append(f"{m.group(1)} – {m.group(2)}")
    return " · ".join(parts)
