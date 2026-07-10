#!/usr/bin/env python3
"""
Export quotidien des données publiques vers OVH via FTP.
Config FTP : ~/.survalerte/ftp.json (jamais dans le dépôt git)
Cron Pi : 0 2 * * * /home/david/survalerte/export_public.py >> /home/david/export_public.log 2>&1

Champs optionnels dans ftp.json pour les notifications email :
  "smtp_host": "ssl0.ovh.net",
  "smtp_port": 465,
  "smtp_user": "user@domaine.com",
  "smtp_password": "...",
  "email_to": "destinataire@domaine.com"
"""

import ftplib
import io
import json
import os
import smtplib
import sqlite3
import sys
import traceback
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

import config

FTP_CONFIG_PATH = os.path.expanduser("~/.survalerte/ftp.json")
STATUS_PATH = os.path.expanduser("~/.survalerte/export_status.txt")

FTP_DEFAULTS = {
    "host": "",
    "user": "",
    "password": "",
    "path": "/survalerte/public_data.json",
    "passive": True,
    "tls": True,
    "nom_zone": "",
}


def load_ftp_config() -> dict:
    if os.path.exists(FTP_CONFIG_PATH):
        with open(FTP_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return {**FTP_DEFAULTS, **data}
    return dict(FTP_DEFAULTS)


def save_status(ok: bool, msg: str) -> None:
    os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        f.write(f"{'OK' if ok else 'ERR'}|{ts}|{msg}\n")


def send_email(ftp_cfg: dict, subject: str, body: str) -> None:
    host = ftp_cfg.get("smtp_host", "")
    if not host:
        return
    port = int(ftp_cfg.get("smtp_port", 465))
    user = ftp_cfg.get("smtp_user", "")
    pwd = ftp_cfg.get("smtp_password", "")
    to = ftp_cfg.get("email_to", user)
    if not (user and pwd and to):
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.set_content(body)

    try:
        with smtplib.SMTP_SSL(host, port) as smtp:
            smtp.login(user, pwd)
            smtp.send_message(msg)
        print(f"  Email envoyé → {to}")
    except Exception as exc:
        print(f"  [WARN] Envoi email échoué : {exc}")


def fetch_survols() -> list[dict]:
    with sqlite3.connect(config.DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT date, heure, icao24, indicatif,
                      altitude_m, vitesse_kmh, cap_deg, pays, lat, lon, infraction
               FROM survols
               ORDER BY timestamp DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def build_payload(survols: list[dict], cfg: dict, ftp_cfg: dict) -> dict:
    hier = (date.today() - timedelta(days=1)).isoformat()
    nom_zone = (
        ftp_cfg.get("nom_zone")
        or cfg.get("profil", {}).get("ville")
        or "Zone surveillée"
    )
    infractions = sum(1 for s in survols if s.get("infraction"))
    first_date = survols[-1]["date"] if survols else None

    return {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "data_jusqu_au": hier,
            "nom_zone": nom_zone,
            "lat": cfg["lat"],
            "lon": cfg["lon"],
            "rayon_km": cfg["rayon_km"],
            "alt_min_legale": cfg["alt_min_legale"],
            "heure_nuit_deb": cfg["heure_nuit_deb"],
            "heure_nuit_fin": cfg["heure_nuit_fin"],
        },
        "stats": {
            "total": len(survols),
            "infractions": infractions,
            "first_date": first_date,
        },
        "survols": survols,
    }


def upload_ftp(json_bytes: bytes, ftp_cfg: dict) -> None:
    cls = ftplib.FTP_TLS if ftp_cfg.get("tls", True) else ftplib.FTP
    path = ftp_cfg["path"]
    directory = "/".join(path.split("/")[:-1])
    with cls(ftp_cfg["host"]) as ftp:
        ftp.login(ftp_cfg["user"], ftp_cfg["password"])
        if ftp_cfg.get("tls", True):
            ftp.prot_p()
        ftp.set_pasv(ftp_cfg.get("passive", True))
        if directory:
            try:
                ftp.mkd(directory)
            except ftplib.error_perm:
                pass  # dossier déjà existant
        ftp.storbinary(f"STOR {path}", io.BytesIO(json_bytes))
    print(f"[OK] Upload FTP → {ftp_cfg['host']}{path}")


def export() -> None:
    cfg = config.load()
    ftp_cfg = load_ftp_config()
    hier = (date.today() - timedelta(days=1)).isoformat()

    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Export public — données jusqu'au {hier}")

    survols = fetch_survols()
    print(f"  {len(survols)} survols chargés depuis la BDD")

    payload = build_payload(survols, cfg, ftp_cfg)
    json_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    print(f"  JSON : {len(json_bytes) / 1024:.1f} Ko")

    if not ftp_cfg.get("host"):
        out = Path(__file__).parent / "public_data.json"
        out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        msg = f"FTP non configuré — fichier écrit localement : {out}"
        print(f"  {msg}")
        print(f"  Pour configurer le FTP, créer : {FTP_CONFIG_PATH}")
        save_status(False, "FTP non configuré")
        return

    try:
        upload_ftp(json_bytes, ftp_cfg)
        msg = f"{len(survols)} survols, {hier}"
        save_status(True, msg)
    except Exception:
        tb = traceback.format_exc()
        print(f"[ERREUR] Upload FTP :\n{tb}", file=sys.stderr)
        err_msg = tb.strip().splitlines()[-1]
        save_status(False, err_msg)
        send_email(
            ftp_cfg,
            subject="[SurvAlerte] Échec export FTP",
            body=(
                f"L'export public du {datetime.now():%d/%m/%Y à %H:%M} a échoué.\n\n"
                f"Erreur :\n{tb}\n\n"
                f"Vérifier : {FTP_CONFIG_PATH}\n"
                f"Log complet : ~/export_public.log"
            ),
        )
        sys.exit(1)


if __name__ == "__main__":
    export()
