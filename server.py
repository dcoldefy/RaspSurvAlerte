"""
Serveur Flask — interface web RaspSurAlert.
Lance le scanner au démarrage, sert le dashboard et les réglages.
"""
from flask import Flask, render_template, jsonify, request, redirect, url_for

import config
from database import load_all, clear_db, get_stats
from api import chercher_communes, chercher_coordonnees_commune
from scanner import Scanner
from utils import fmt_alt, fmt_val, fmt_pays, get_code, get_css_class, get_badge

app     = Flask(__name__)
scanner = Scanner()


# ── Helpers Jinja2 ─────────────────────────────────────────────────────────

app.jinja_env.globals.update(
    fmt_alt=fmt_alt,
    fmt_val=fmt_val,
    fmt_pays=fmt_pays,
    get_code=get_code,
    get_css_class=get_css_class,
    get_badge=get_badge,
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
    rows   = load_all()
    result = []
    for r in rows:
        (date, heure, ts, icao24, indicatif, alt_m, alt_geo,
         vitesse, cap, au_sol, pays, lat, lon, infraction) = r
        code = get_code(infraction or "")
        result.append({
            "date": date, "heure": heure, "icao24": icao24,
            "indicatif":   indicatif,
            "altitude_m":  alt_m,
            "vitesse_kmh": vitesse,
            "cap_deg":     cap,
            "pays":        pays,
            "infraction":  infraction or "",
            "code":        code,
            "css_class":   get_css_class(code),
            "badge":       get_badge(code),
        })
    return jsonify(result)


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


@app.route("/api/status")
def api_status():
    st = scanner.get_state()
    return jsonify({
        "status":    st["status"],
        "status_ok": st["status_ok"],
        "last_scan": st["last_scan"],
        "n_infr":    st["n_infr"],
    })


@app.route("/api/communes")
def api_communes():
    cp = request.args.get("cp", "").strip()
    if not cp:
        return jsonify([])
    return jsonify(chercher_communes(cp))


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
    cfg["alt_min_legale"] = int(request.form.get("alt_min_legale", 1000))
    cfg["heure_nuit_deb"] = int(request.form.get("heure_nuit_deb", 22))
    cfg["heure_nuit_fin"] = int(request.form.get("heure_nuit_fin", 6))
    cfg["rayon_km"]       = int(request.form.get("rayon_km", 3))
    config.save(cfg)
    return redirect(url_for("reglages") + "?ok=seuils")


@app.route("/effacer", methods=["POST"])
def effacer():
    clear_db()
    scanner.clear_flights()
    return redirect(url_for("index"))


# ── Point d'entrée ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    scanner.start()
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
