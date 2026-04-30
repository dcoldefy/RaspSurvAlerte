"""
Serveur Flask — interface web RaspSurAlert.
Lance le scanner au démarrage, sert le dashboard et les réglages.
"""
import re
import secrets as _secrets
import signal
from flask import Flask, render_template, jsonify, request, redirect, url_for, Response, session
from werkzeug.security import check_password_hash, generate_password_hash

import config
from database import (init_db, load_all, clear_db, get_stats,
                      create_user, get_user_by_token, list_users, delete_user)
from api import chercher_communes, chercher_coordonnees_commune
from scanner import Scanner
from utils import fmt_alt, fmt_val, fmt_dist, fmt_pays, fmt_heure, get_code, get_css_class, get_badge, get_seuil_display, distance_km
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
app = Flask(__name__)
app.jinja_env.globals['css_version'] = int(time.time())

# Clé secrète pour les sessions (générée une fois, stockée dans config)
_cfg_init = config.load()
if not _cfg_init.get('secret_key'):
    _cfg_init['secret_key'] = _secrets.token_hex(32)
    config.save(_cfg_init)
app.secret_key = _cfg_init['secret_key']

init_db()
scanner = Scanner()


# ── Auth ───────────────────────────────────────────────────────────────────

@app.context_processor
def inject_auth():
    return {'is_admin': bool(session.get('is_admin'))}


def _access_level():
    """Retourne 'admin', 'user' ou None."""
    if session.get('is_admin'):
        return 'admin'
    token = request.args.get('token', '').strip() or session.get('user_token', '')
    if token and get_user_by_token(token):
        session['user_token'] = token
        return 'user'
    return None


def _get_profil():
    """Retourne le profil à utiliser : celui de l'utilisateur connecté ou le profil global."""
    token = session.get('user_token', '')
    if token:
        user = get_user_by_token(token)
        if user:
            # (id, token, nom, prenom, adresse, code_postal, ville, created_at)
            return {
                "nom":         user[2],
                "prenom":      user[3],
                "adresse":     user[4],
                "code_postal": user[5],
                "ville":       user[6],
            }
    return config.load().get("profil", {})


# ── Helpers Jinja2 ─────────────────────────────────────────────────────────

app.jinja_env.globals.update(
    fmt_alt=fmt_alt,
    fmt_heure=fmt_heure,
    fmt_val=fmt_val,
    fmt_dist=fmt_dist,
    fmt_pays=fmt_pays,
    get_code=get_code,
    get_css_class=get_css_class,
    get_badge=get_badge,
    get_seuil_display=get_seuil_display,
    distance_km=distance_km,
)


# ── PWA ────────────────────────────────────────────────────────────────────

@app.route("/sw.js")
def service_worker():
    return app.send_static_file("sw.js"), 200, {"Content-Type": "application/javascript"}


@app.route("/manifest.json")
def manifest():
    return app.send_static_file("manifest.json"), 200, {"Content-Type": "application/manifest+json"}


# ── Auth routes ────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    cfg = config.load()
    password_hash = cfg.get('admin_password_hash', '')
    first_time = not password_hash

    if request.method == "POST":
        password = request.form.get('password', '').strip()
        if first_time:
            if len(password) >= 4:
                cfg['admin_password_hash'] = generate_password_hash(password)
                config.save(cfg)
                session['is_admin'] = True
                return redirect(url_for('index'))
            return render_template('login.html', first_time=True,
                                   error="Mot de passe trop court (4 caractères minimum).")
        if check_password_hash(password_hash, password):
            session['is_admin'] = True
            return redirect(url_for('index'))
        return render_template('login.html', first_time=False,
                               error="Mot de passe incorrect.")

    return render_template('login.html', first_time=first_time)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── Pages ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    access = _access_level()
    if access is None:
        return redirect(url_for('login'))
    cfg   = config.load()
    rows  = load_all()
    stats = get_stats()
    state = scanner.get_state()
    return render_template("index.html", cfg=cfg, rows=rows, stats=stats, state=state)


@app.route("/reglages")
def reglages():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    cfg = config.load()
    return render_template("reglages.html", cfg=cfg)


@app.route("/admin/users")
def admin_users():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    users = list_users()
    scheme = request.headers.get('X-Forwarded-Proto', request.scheme)
    base_url = f"{scheme}://{request.host}"
    return render_template('admin_users.html', users=users, base_url=base_url)


@app.route("/admin/users/create", methods=["POST"])
def create_user_route():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    nom         = request.form.get('nom', '').strip().upper()
    prenom      = request.form.get('prenom', '').strip().capitalize()
    adresse     = request.form.get('adresse', '').strip()
    code_postal = request.form.get('code_postal', '').strip()
    ville       = request.form.get('ville', '').strip().upper()
    if nom and prenom:
        create_user(nom, prenom, adresse, code_postal, ville)
    return redirect(url_for('admin_users'))


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
    cfg = config.load()
    return jsonify({
        "status":           status,
        "status_ok":        st["status_ok"],
        "last_scan":        st["last_scan"],
        "n_infr":           st["n_infr"],
        "error_count":      st["error_count"],
        "last_error_type":  st["last_error_type"],
        "opensky_credits":  st.get("opensky_credits"),
        "source":           cfg.get("source", "flightradar24"),
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
    profil = _get_profil()
    ville  = profil.get("ville", "")
    cp     = profil.get("code_postal", "")
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

    profil = _get_profil()

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
    if not session.get('is_admin'):
        return redirect(url_for('login'))
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
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    cfg = config.load()
    cfg["alt_min_legale"] = max(0, int(request.form.get("alt_min_legale", 1000)))
    cfg["heure_nuit_deb"] = max(0, min(23.5, float(request.form.get("heure_nuit_deb", 22))))
    cfg["heure_nuit_fin"] = max(0, min(23.5, float(request.form.get("heure_nuit_fin", 6))))
    cfg["rayon_km"]       = max(1, min(50, int(request.form.get("rayon_km", 3))))
    config.save(cfg)
    return redirect(url_for("reglages") + "?ok=seuils")


@app.route("/reglages/source", methods=["POST"])
def save_source():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    cfg = config.load()
    source = request.form.get("source", "flightradar24")
    if source in ("opensky", "flightradar24"):
        cfg["source"] = source
        config.save(cfg)
    return redirect(url_for("reglages") + "?ok=source")


@app.route("/reglages/opensky", methods=["POST"])
def save_opensky():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    cfg = config.load()
    cfg["opensky_user"] = request.form.get("opensky_user", "").strip()
    cfg["opensky_pass"] = request.form.get("opensky_pass", "")
    config.save(cfg)
    return redirect(url_for("reglages") + "?ok=opensky")


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
def delete_user_route(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    delete_user(user_id)
    return redirect(url_for('admin_users'))


@app.route("/reglages/password", methods=["POST"])
def save_password():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    cfg = config.load()
    password = request.form.get('password', '').strip()
    if len(password) >= 4:
        cfg['admin_password_hash'] = generate_password_hash(password)
        config.save(cfg)
    return redirect(url_for('reglages') + "?ok=password")


@app.route("/effacer", methods=["POST"])
def effacer():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    clear_db()
    scanner.clear_flights()
    return redirect(url_for("index"))


# ── Point d'entrée ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    def _shutdown(signum, frame):
        scanner.stop()
    signal.signal(signal.SIGTERM, _shutdown)

    scanner.start()
    from pathlib import Path
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True, ssl_context=None)
