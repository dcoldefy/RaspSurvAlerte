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
                      create_user, get_user_by_token, get_user_by_id,
                      update_user_last_seen, update_user_destinataires,
                      update_user_info, list_users, delete_user)
from api import chercher_communes, chercher_coordonnees_commune
from scanner import Scanner
from utils import fmt_alt, fmt_val, fmt_dist, fmt_pays, fmt_heure, get_code, get_css_class, get_badge, get_seuil_display, distance_km
from pdf import generer_plainte_pdf_bytes, generer_plainte_texte

# Destinataires — modèle par défaut (3 fixes pré-cochés, 2 à remplir)
DESTINATAIRES_DEFAUT = [
    {
        "id":          "acnusa",
        "label":       "ACNUSA",
        "nom":         "Autorité de Contrôle des Nuisances Sonores Aéroportuaires (ACNUSA)",
        "adresse":     "244 Bd Saint-Germain\n75007 PARIS",
        "email":       "contact@acnusa.fr",
        "selectionne": True,
        "fixe":        True,
        "email_fixe":  True,
    },
    {
        "id":          "maison",
        "label":       "Maison de l'Environnement",
        "nom":         "Maison de l'Environnement Roissy Charles de Gaulle",
        "adresse":     "1, rue de France - BP 81007\n95931 Roissy Charles de Gaulle Cedex",
        "email":       "environnement.cdg@adp.fr",
        "selectionne": True,
        "fixe":        True,
        "email_fixe":  True,
    },
    {
        "id":          "ministre",
        "label":       "Ministre de la Transition écologique",
        "nom":         "Monsieur le Ministre de la Transition écologique",
        "adresse":     "Hôtel de Roquelaure - 246, Boulevard Saint-Germain\n75007 PARIS",
        "email":       "",
        "selectionne": True,
        "fixe":        True,
    },
    {
        "id":          "mairie",
        "label":       "Mairie",
        "nom":         "",
        "adresse":     "",
        "email":       "",
        "selectionne": False,
        "fixe":        False,
    },
    {
        "id":          "depute",
        "label":       "Député(e)",
        "nom":         "",
        "adresse":     "",
        "email":       "",
        "selectionne": False,
        "fixe":        False,
    },
]

import copy
import json
import time
from datetime import timedelta
app = Flask(__name__)
app.jinja_env.globals['css_version'] = int(time.time())
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)

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
    already_in_session = bool(session.get('user_token', ''))
    token = (request.args.get('token', '').strip()
             or session.get('user_token', '')
             or request.cookies.get('user_token', ''))
    if token and get_user_by_token(token):
        session.permanent = True
        session['user_token'] = token
        if not request.path.startswith('/api'):
            update_user_last_seen(token)
        return 'user'
    return None


@app.after_request
def _set_token_cookie(response):
    """Pose un cookie persistant user_token à chaque réponse authentifiée."""
    token = session.get('user_token', '')
    if token:
        response.set_cookie(
            'user_token', token,
            max_age=365 * 24 * 3600,
            httponly=True,
            samesite='Lax',
        )
    return response


def _get_profil():
    """Retourne le profil à utiliser : celui de l'utilisateur connecté ou le profil global."""
    token = session.get('user_token', '')
    if token:
        user = get_user_by_token(token)
        if user:
            # (id, token, nom, prenom, adresse, code_postal, ville, depute_civilite, depute_nom, created_at)
            return {
                "nom":             user[2],
                "prenom":          user[3],
                "adresse":         user[4],
                "code_postal":     user[5],
                "ville":           user[6],
                "depute_civilite": user[7],
                "depute_nom":      user[8],
            }
    return config.load().get("profil", {})


def _get_destinataires_user():
    """Retourne la liste des destinataires de l'utilisateur connecté (ou défaut)."""
    token = session.get('user_token', '')
    if token:
        user = get_user_by_token(token)
        if user and user[11]:
            return json.loads(user[11])
    return copy.deepcopy(DESTINATAIRES_DEFAUT)


def _parse_destinataires_from_form(form):
    """Construit la liste des destinataires depuis les données de formulaire POST."""
    result = []
    for d in copy.deepcopy(DESTINATAIRES_DEFAUT):
        did = d["id"]
        d["selectionne"] = f"dest_{did}_sel" in form
        if not d.get("email_fixe"):
            d["email"] = form.get(f"dest_{did}_email", "").strip()
        if not d["fixe"]:
            d["nom"]     = form.get(f"dest_{did}_nom", "").strip()
            d["adresse"] = form.get(f"dest_{did}_adresse", "").strip()
        result.append(d)
    return result


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
        # Connexion par lien/token utilisateur
        raw_token = request.form.get('user_token', '').strip()
        if raw_token:
            # Accepte une URL complète ou juste le token
            if '?token=' in raw_token:
                raw_token = raw_token.split('?token=')[1].split('&')[0]
            user = get_user_by_token(raw_token)
            if user:
                session.permanent = True
                session['user_token'] = raw_token
                resp = redirect(url_for('index'))
                resp.set_cookie('user_token', raw_token,
                                max_age=365 * 24 * 3600,
                                httponly=True, samesite='Lax')
                return resp
            return render_template('login.html', first_time=first_time,
                                   error_token="Lien invalide ou expiré.")

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
    resp = redirect(url_for('login'))
    resp.delete_cookie('user_token')
    return resp


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
    return render_template('admin_users.html', users=users, base_url=base_url,
                           destinataires_defaut=DESTINATAIRES_DEFAUT)


@app.route("/admin/users/create", methods=["POST"])
def create_user_route():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    nom             = request.form.get('nom', '').strip().upper()
    prenom          = request.form.get('prenom', '').strip().capitalize()
    adresse         = request.form.get('adresse', '').strip()
    code_postal     = request.form.get('code_postal', '').strip()
    ville           = request.form.get('ville', '').strip().upper()
    depute_civilite = request.form.get('depute_civilite', 'M.').strip()
    depute_nom      = request.form.get('depute_nom', '').strip()
    if nom and prenom:
        destinataires = _parse_destinataires_from_form(request.form)
        create_user(nom, prenom, adresse, code_postal, ville,
                    depute_civilite, depute_nom, destinataires)
    return redirect(url_for('admin_users'))


@app.route("/admin/users/<int:uid>/edit", methods=["GET", "POST"])
def admin_user_edit(uid):
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    user = get_user_by_id(uid)
    if not user:
        return redirect(url_for('admin_users'))
    if request.method == "POST":
        nom         = request.form.get("nom", "").strip().upper()
        prenom      = request.form.get("prenom", "").strip()
        adresse     = request.form.get("adresse", "").strip()
        code_postal = request.form.get("code_postal", "").strip()
        ville       = request.form.get("ville", "").strip()
        update_user_info(uid, nom, prenom, adresse, code_postal, ville)
        destinataires = _parse_destinataires_from_form(request.form)
        update_user_destinataires(uid, destinataires)
        return redirect(url_for('admin_users'))
    stored = json.loads(user[11]) if user[11] else copy.deepcopy(DESTINATAIRES_DEFAUT)
    return render_template('admin_user_edit.html', user=user, destinataires=stored)


@app.route("/admin/users/<int:uid>/destinataires", methods=["GET", "POST"])
def admin_user_destinataires(uid):
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    user = get_user_by_id(uid)
    if not user:
        return redirect(url_for('admin_users'))
    if request.method == "POST":
        destinataires = _parse_destinataires_from_form(request.form)
        update_user_destinataires(uid, destinataires)
        return redirect(url_for('admin_users'))
    stored = json.loads(user[11]) if user[11] else copy.deepcopy(DESTINATAIRES_DEFAUT)
    return render_template('admin_user_destinataires.html', user=user, destinataires=stored)


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
    dests = _get_destinataires_user()
    result = [
        {"id": d["id"], "label": d["label"], "nom": d["nom"], "adresse": d["adresse"], "email": d["email"]}
        for d in dests if d.get("selectionne") and d.get("nom")
    ]
    return jsonify(result)


@app.route("/api/plainte", methods=["POST"])
def api_plainte():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Requête JSON invalide."}), 400
    vol         = data.get("vol", {})
    dest_id     = data.get("destinataire_id", "")
    profil      = _get_profil()

    if not profil.get("nom") or not profil.get("prenom"):
        return jsonify({"error": "Profil incomplet — renseignez votre nom et prénom."}), 400

    dests = _get_destinataires_user()
    dest  = next((d for d in dests if d["id"] == dest_id and d.get("selectionne") and d.get("nom")), None)
    if not dest:
        return jsonify({"error": "Destinataire invalide ou non configuré."}), 400

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


@app.route("/api/plainte/email", methods=["POST"])
def api_plainte_email():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Requête JSON invalide."}), 400
    vol     = data.get("vol", {})
    dest_id = data.get("destinataire_id", "")
    profil  = _get_profil()

    if not profil.get("nom") or not profil.get("prenom"):
        return jsonify({"error": "Profil incomplet — renseignez votre nom et prénom."}), 400

    dests = _get_destinataires_user()
    dest  = next((d for d in dests if d["id"] == dest_id and d.get("selectionne") and d.get("email")), None)
    if not dest:
        return jsonify({"error": "Destinataire invalide ou sans email configuré."}), 400

    subject, body = generer_plainte_texte(profil, vol, dest)
    return jsonify({"to": dest["email"], "subject": subject, "body": body})


# ── Actions ────────────────────────────────────────────────────────────────

@app.route("/reglages/profil", methods=["POST"])
def save_profil():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    cfg = config.load()
    cp  = request.form.get("code_postal", "").strip()
    vil = request.form.get("ville", "").strip().upper()
    cfg["profil"] = {
        "nom":             request.form.get("nom", "").strip().upper(),
        "prenom":          request.form.get("prenom", "").strip().capitalize(),
        "adresse":         request.form.get("adresse", "").strip(),
        "code_postal":     cp,
        "ville":           vil,
        "depute_civilite": request.form.get("depute_civilite", "M.").strip(),
        "depute_nom":      request.form.get("depute_nom", "").strip(),
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
