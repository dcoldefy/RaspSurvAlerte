"""
Couche base de données SQLite — création, lecture, écriture des survols et utilisateurs.
"""
import secrets
import sqlite3
import time
from datetime import datetime

from config import DB_FILE, DEDUP_WINDOW

SCHEMA_VERSION = 5


def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS survols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, heure TEXT, timestamp INTEGER,
            icao24 TEXT, indicatif TEXT,
            altitude_m INTEGER, altitude_geo INTEGER,
            vitesse_kmh INTEGER, cap_deg INTEGER,
            au_sol INTEGER, pays TEXT, lat REAL, lon REAL, infraction TEXT)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ts ON survols(timestamp)")

        c.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")
        row = c.execute("SELECT version FROM schema_version").fetchone()
        current = row[0] if row else 0

        if current < 2:
            c.execute("""CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT UNIQUE NOT NULL,
                nom TEXT NOT NULL,
                prenom TEXT NOT NULL,
                created_at TEXT NOT NULL)""")

        if current < 3:
            c.execute("ALTER TABLE users ADD COLUMN adresse TEXT NOT NULL DEFAULT ''")
            c.execute("ALTER TABLE users ADD COLUMN code_postal TEXT NOT NULL DEFAULT ''")
            c.execute("ALTER TABLE users ADD COLUMN ville TEXT NOT NULL DEFAULT ''")

        if current < 4:
            c.execute("ALTER TABLE users ADD COLUMN depute_civilite TEXT NOT NULL DEFAULT 'M.'")
            c.execute("ALTER TABLE users ADD COLUMN depute_nom TEXT NOT NULL DEFAULT ''")

        if current < 5:
            c.execute("ALTER TABLE survols ADD COLUMN taux_montee INTEGER")

        if current < SCHEMA_VERSION:
            c.execute("DELETE FROM schema_version")
            c.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()


def save_passage(row):
    """Insère un nouveau survol et retourne son id."""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO survols
            (date,heure,timestamp,icao24,indicatif,altitude_m,altitude_geo,
             vitesse_kmh,cap_deg,au_sol,pays,lat,lon,infraction)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (row["date"], row["heure"], row["timestamp"], row["icao24"], row["indicatif"],
             row["altitude_m"], row["altitude_geo"], row["vitesse_kmh"], row["cap_deg"],
             row["au_sol"], row["pays"], row["lat"], row["lon"], row["infraction"]))
        row_id = c.lastrowid
        conn.commit()
    return row_id


def update_passage(db_id, row):
    """Met à jour les données dynamiques d'un vol existant."""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""UPDATE survols SET
            altitude_m=?, altitude_geo=?, vitesse_kmh=?, cap_deg=?,
            lat=?, lon=?, infraction=?, timestamp=?
            WHERE id=?""",
            (row["altitude_m"], row["altitude_geo"], row["vitesse_kmh"], row["cap_deg"],
             row["lat"], row["lon"], row["infraction"], row["timestamp"], db_id))
        conn.commit()


def get_active_flights():
    """Vols vus dans la fenêtre DEDUP_WINDOW : {icao24: {id, has_infraction, last_seen}}."""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        cutoff = int(time.time()) - DEDUP_WINDOW
        c.execute("""SELECT icao24, id, infraction, MAX(timestamp) as last_seen
                     FROM survols WHERE timestamp>=? GROUP BY icao24""", (cutoff,))
        result = {}
        for icao24, db_id, infraction, last_seen in c.fetchall():
            result[icao24] = {
                "id": db_id,
                "has_infraction": bool(infraction),
                "last_seen": last_seen,
            }
    return result


def load_all():
    """Retourne tous les survols triés du plus récent au plus ancien."""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""SELECT date,heure,timestamp,icao24,indicatif,altitude_m,altitude_geo,
                            vitesse_kmh,cap_deg,au_sol,pays,lat,lon,infraction
                     FROM survols ORDER BY timestamp DESC""")
        rows = c.fetchall()
    return rows


def get_stats():
    """Retourne un dict de statistiques agrégées."""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM survols")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM survols WHERE infraction IS NOT NULL AND infraction != ''")
        n_infr = c.fetchone()[0]
        c.execute("SELECT heure, indicatif FROM survols ORDER BY timestamp DESC LIMIT 1")
        last = c.fetchone()
    return {
        "total": total,
        "infractions": n_infr,
        "last_heure": last[0] if last else None,
        "last_indicatif": last[1] if last else None,
    }


def clear_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.cursor().execute("DELETE FROM survols")
        conn.commit()


# ── Utilisateurs ───────────────────────────────────────────────────────────

def create_user(nom, prenom, adresse, code_postal, ville, depute_civilite="M.", depute_nom=""):
    """Crée un utilisateur, retourne le token généré."""
    token = secrets.token_urlsafe(32)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT INTO users (token, nom, prenom, adresse, code_postal, ville, depute_civilite, depute_nom, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (token, nom, prenom, adresse, code_postal, ville, depute_civilite, depute_nom, created_at),
        )
    return token


def get_user_by_token(token):
    """Retourne (id, token, nom, prenom, adresse, code_postal, ville, depute_civilite, depute_nom, created_at) ou None."""
    with sqlite3.connect(DB_FILE) as conn:
        return conn.execute(
            "SELECT id, token, nom, prenom, adresse, code_postal, ville, depute_civilite, depute_nom, created_at FROM users WHERE token = ?",
            (token,),
        ).fetchone()


def list_users():
    """Retourne tous les utilisateurs triés par date de création."""
    with sqlite3.connect(DB_FILE) as conn:
        return conn.execute(
            "SELECT id, token, nom, prenom, adresse, code_postal, ville, depute_civilite, depute_nom, created_at FROM users ORDER BY created_at DESC"
        ).fetchall()


def delete_user(user_id):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
