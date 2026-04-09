"""
Couche base de données SQLite — création, lecture, écriture des survols.
"""
import sqlite3
import time

from config import DB_FILE, DEDUP_WINDOW


def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS survols (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, heure TEXT, timestamp INTEGER,
        icao24 TEXT, indicatif TEXT,
        altitude_m INTEGER, altitude_geo INTEGER,
        vitesse_kmh INTEGER, cap_deg INTEGER,
        au_sol INTEGER, pays TEXT, lat REAL, lon REAL, infraction TEXT)""")
    conn.commit()
    conn.close()


def save_passage(row):
    """Insère un nouveau survol et retourne son id."""
    conn = sqlite3.connect(DB_FILE)
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
    conn.close()
    return row_id


def update_passage(db_id, row):
    """Met à jour les données dynamiques d'un vol existant."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""UPDATE survols SET
        altitude_m=?, altitude_geo=?, vitesse_kmh=?, cap_deg=?,
        lat=?, lon=?, infraction=?, timestamp=?
        WHERE id=?""",
        (row["altitude_m"], row["altitude_geo"], row["vitesse_kmh"], row["cap_deg"],
         row["lat"], row["lon"], row["infraction"], row["timestamp"], db_id))
    conn.commit()
    conn.close()


def get_active_flights():
    """Vols vus dans la fenêtre DEDUP_WINDOW : {icao24: {id, has_infraction, last_seen}}."""
    conn = sqlite3.connect(DB_FILE)
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
    conn.close()
    return result


def load_all():
    """Retourne tous les survols triés du plus récent au plus ancien."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""SELECT date,heure,timestamp,icao24,indicatif,altitude_m,altitude_geo,
                        vitesse_kmh,cap_deg,au_sol,pays,lat,lon,infraction
                 FROM survols ORDER BY timestamp DESC""")
    rows = c.fetchall()
    conn.close()
    return rows


def get_stats():
    """Retourne un dict de statistiques agrégées."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM survols")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM survols WHERE infraction IS NOT NULL AND infraction != ''")
    n_infr = c.fetchone()[0]
    c.execute("SELECT heure, indicatif FROM survols ORDER BY timestamp DESC LIMIT 1")
    last = c.fetchone()
    conn.close()
    return {
        "total": total,
        "infractions": n_infr,
        "last_heure": last[0] if last else None,
        "last_indicatif": last[1] if last else None,
    }


def clear_db():
    conn = sqlite3.connect(DB_FILE)
    conn.cursor().execute("DELETE FROM survols")
    conn.commit()
    conn.close()
