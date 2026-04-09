"""
Serveur Flask — interface web RaspSurAlert.
Lance le scanner au démarrage, sert le dashboard et les réglages.
"""
import re
import signal
from flask import Flask, render_template, jsonify, request, redirect, url_for, Response

import config
from database import init_db, load_all, clear_db, get_stats
from api import chercher_communes, chercher_coordonnees_commune
from scanner import Scanner
from utils import fmt_alt, fmt_val, fmt_dist, fmt_pays, get_code, get_css_class, get_badge, get_seuil_display, distance_km
from pdf import generer_plainte_pdf_bytes

# Destinataires disponibles pour la génération de plainte
DESTINATAIRES = [
    {
        "label":    "ACNUSA",
        "nom":      "Autorité de Contrôle des Nuisances Sonores Aéroportuaires (ACNUSA)",
        "adresse":  "244 Bd Saint-Germain",
        "cp_ville": "75007 PARIS",
    },
    {
        "label":    "Maison de l'Environnement Roissy CDG",
        "nom":      "Maison de l'Environnement Roissy Charles de Gaulle",
        "adresse":  "1, rue de France - BP 81007",
        "cp_ville": "95931 Roissy Charles de Gaulle Cedex",
    },
    {
        "label":    "Ministre de la Transition écologique",
        "nom":      "Monsieur le Ministre de la Transition écologique",
        "adresse":  "Hôtel de Roquelaure - 246, Boulevard Saint-Germain",
        "cp_ville": "75007 PARIS",
    },
    {
        "label":    "Mairie de ma commune",
        "nom":      None,   # Rempli dynamiquement depuis le profil
        "adresse":  None,
        "cp_ville": None,
    },
]

import time
app     = Flask(__name__)
app.jinja_env.globals['css_version'] = int(time.time())
init_db()   # garantit que la table existe avant toute requête HTTP
scanner = Scanner()


# ── Helpers Jinja2 ─────────────────────────────────────────────────────────

app.jinja_env.globals.update(
    fmt_alt=fmt_alt,
    fmt_val=fmt_val,
    fmt_dist=fmt_dist,
    fmt_pays=fmt_pays,
    get_code=get_code,
    get_css_class=get_css_class,
    get_badge=get_badge,
    get_seuil_display=get_seuil_display,
    distance_km=distance_km,
)


# ── Pages ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    cfg   = config.load()
    rows  = load_all()
    stats = get_stats()
    state = scanner.get_state()
    return render_template("index.html",
                           cfg=cfg, rows=rows, stats=stats, state=state)


@app.route("/reglages")
def reglages():
    cfg = config.load()
    return render_template("reglages.html", cfg=cfg)


# ── API JSON ───────────────────────────────────────────────────────────────

@app.route("/api/survols")
def api_survols():
    rows     = load_all()
    cfg_data = config.load()
    cfg_lat  = cfg_data.get("lat")
    cfg_lon  = cfg_data.get("lon")
    result   = []
    for r in rows:
        (date, heure, ts, icao24, indicatif, alt_m, alt_geo,
         vitesse, cap, au_sol, pays, lat, lon, infraction) = r
        code = get_code(infraction or "")
        dist = distance_km(cfg_lat, cfg_lon, lat, lon)
        result.append({
            "date": date, "heure": heure, "icao24": icao24,
            "indicatif":   indicatif,
            "altitude_m":  alt_m,
            "distance_km": round(dist, 1) if dist is not None else None,
            "vitesse_kmh": vitesse,
            "cap_deg":     cap,
            "pays":        pays,
            "infraction":  infraction or "",
            "code":        code,
            "css_class":   get_css_class(code),
            "badge":       get_badge(code),
            "seuil":       get_seuil_display(code, infraction or ""),
        })
    return jsonify(result)


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


@app.route("/api/status")
def api_status():
    import time as _time
    st = scanner.get_state()
    status = st["status"]
    retry_until = st.get("retry_until")
    if retry_until:
        remaining = max(0, int(retry_until - _time.time()))
        h, rem = divmod(remaining, 3600)
        m, s = divmod(rem, 60)
        if h:
            countdown = f"{h}h{m:02d}m{s:02d}s"
        elif m:
            countdown = f"{m}m{s:02d}s"
        else:
            countdown = f"{s}s"
        status = f"{status} — réessai dans {countdown}"
    return jsonify({
        "status":          status,
        "status_ok":       st["status_ok"],
        "last_scan":       st["last_scan"],
        "n_infr":          st["n_infr"],
        "error_count":     st["error_count"],
        "last_error_type": st["last_error_type"],
    })


@app.route("/api/stream")
def api_stream():
    """SSE — notifie le client dès que le scanner termine un nouveau scan."""
    def generate():
        last_count = -1
        try:
            while True:
                state = scanner.get_state()
                count = state.get("scan_count", 0)
                if count != last_count:
                    last_count = count
                    yield "data: update\n\n"
                else:
                    yield "data: ping\n\n"
                time.sleep(2)
        except GeneratorExit:
            pass
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/communes")
def api_communes():
    cp = request.args.get("cp", "").strip()
    if not re.fullmatch(r'[0-9]{5}', cp):
        return jsonify([])
    return jsonify(chercher_communes(cp))


@app.route("/api/destinataires")
def api_destinataires():
    cfg   = config.load()
    ville = cfg["profil"].get("ville", "")
    cp    = cfg["profil"].get("code_postal", "")
    result = []
    for d in DESTINATAIRES:
        if d["nom"] is None:
            result.append({
                "label":    f"Mairie de {ville}" if ville else "Mairie de ma commune",
                "nom":      f"Monsieur le Maire de {ville}" if ville else "Monsieur le Maire",
                "adresse":  f"Mairie de {ville}" if ville else "",
                "cp_ville": f"{cp} {ville}".strip(),
            })
        else:
            result.append({k: d[k] for k in ("label", "nom", "adresse", "cp_ville")})
    return jsonify(result)


@app.route("/api/plainte", methods=["POST"])
def api_plainte():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Requête JSON invalide."}), 400
    vol      = data.get("vol", {})
    try:
        dest_idx = int(data.get("destinataire_idx", 0))
    except (TypeError, ValueError):
        dest_idx = 0

    cfg    = config.load()
    profil = cfg.get("profil", {})

    if not profil.get("nom") or not profil.get("prenom"):
        return jsonify({"error": "Profil incomplet — renseignez votre nom et prénom dans les Réglages."}), 400

    if dest_idx < 0 or dest_idx >= len(DESTINATAIRES):
        dest_idx = 0

    dest = dict(DESTINATAIRES[dest_idx])
    if dest["nom"] is None:
        ville = profil.get("ville", "")
        cp    = profil.get("code_postal", "")
        dest["nom"]      = f"Monsieur le Maire de {ville}"
        dest["adresse"]  = f"Mairie de {ville}"
        dest["cp_ville"] = f"{cp} {ville}".strip()

    try:
        pdf_bytes = generer_plainte_pdf_bytes(profil, vol, dest)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    indicatif = (vol.get("indicatif") or vol.get("icao24") or "plainte").strip()
    date_str  = (vol.get("date") or "").replace("/", "")
    filename  = f"Plainte_{indicatif}_{date_str}.pdf"

    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Actions ────────────────────────────────────────────────────────────────

@app.route("/reglages/profil", methods=["POST"])
def save_profil():
    cfg = config.load()
    cp  = request.form.get("code_postal", "").strip()
    vil = request.form.get("ville", "").strip().upper()
    cfg["profil"] = {
        "nom":         request.form.get("nom", "").strip().upper(),
        "prenom":      request.form.get("prenom", "").strip().capitalize(),
        "adresse":     request.form.get("adresse", "").strip(),
        "code_postal": cp,
        "ville":       vil,
    }
    lat, lon = chercher_coordonnees_commune(
        cp, vil, cfg.get("lat", 48.9897), cfg.get("lon", 2.0939))
    cfg["lat"] = lat
    cfg["lon"] = lon
    config.save(cfg)
    return redirect(url_for("reglages") + "?ok=profil")


@app.route("/reglages/seuils", methods=["POST"])
def save_seuils():
    cfg = config.load()
    cfg["alt_min_legale"] = max(0, int(request.form.get("alt_min_legale", 1000)))
    cfg["heure_nuit_deb"] = max(0, min(23, int(request.form.get("heure_nuit_deb", 22))))
    cfg["heure_nuit_fin"] = max(0, min(23, int(request.form.get("heure_nuit_fin", 6))))
    cfg["rayon_km"]       = max(1, min(50, int(request.form.get("rayon_km", 3))))
    config.save(cfg)
    return redirect(url_for("reglages") + "?ok=seuils")


@app.route("/reglages/opensky", methods=["POST"])
def save_opensky():
    cfg = config.load()
    cfg["opensky_user"] = request.form.get("opensky_user", "").strip()
    cfg["opensky_pass"] = request.form.get("opensky_pass", "")
    config.save(cfg)
    return redirect(url_for("reglages") + "?ok=opensky")


@app.route("/effacer", methods=["POST"])
def effacer():
    clear_db()
    scanner.clear_flights()
    return redirect(url_for("index"))


# ── Point d'entrée ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    def _shutdown(signum, frame):
        scanner.stop()
    signal.signal(signal.SIGTERM, _shutdown)

    scanner.start()
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
