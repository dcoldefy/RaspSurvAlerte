"""
Thread de scan OpenSky — interroge l'API toutes les 60 s,
maintient l'état partagé accessible par Flask.
"""
import threading
import time
import requests
from datetime import datetime

import config
from database import save_passage, update_passage, get_active_flights, init_db
from filters import est_avion_de_ligne, est_transport_commercial, analyser_infraction
from api import chercher_type_aeronef


class Scanner:
    def __init__(self):
        self.lock  = threading.Lock()
        self.state = {
            "scan_count":          0,
            "last_scan":           None,
            "status":              "En attente du premier scan...",
            "status_ok":           True,
            "active_flights":      {},
            "aircraft_type_cache": {},
            "added":               0,
            "updated":             0,
            "frozen":              0,
            "filtres":             0,
            "n_infr":              0,
            "error_count":         0,
            "error_since":         None,
            "last_error_type":     None,
        }
        self._stop = threading.Event()

    def start(self):
        init_db()
        with self.lock:
            self.state["active_flights"] = get_active_flights()
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while not self._stop.is_set():
            self._do_scan()
            self._stop.wait(config.SCAN_INTERVAL)

    def _do_scan(self):
        cfg = config.load()
        with self.lock:
            self.state["status"]    = "Scan en cours..."
            self.state["status_ok"] = True

        try:
            delta = max(cfg["rayon_km"], 1) / 111.0
            lat, lon = cfg["lat"], cfg["lon"]
            url = (f"https://opensky-network.org/api/states/all"
                   f"?lamin={lat-delta}&lomin={lon-delta}"
                   f"&lamax={lat+delta}&lomax={lon+delta}")

            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            states = [s for s in (resp.json().get("states") or [])
                      if s[5] is not None and s[6] is not None]

            now    = datetime.now()
            now_ts = int(now.timestamp())
            date_s = now.strftime("%d/%m/%Y")
            time_s = now.strftime("%H:%M:%S")

            added = updated = frozen = filtres = n_infr = 0

            with self.lock:
                active_flights      = dict(self.state["active_flights"])
                aircraft_type_cache = self.state["aircraft_type_cache"]

            for s in states:
                icao = (s[0] or "").strip()
                if not icao:
                    continue

                alt_m     = int(s[7])       if s[7] is not None else None
                vitesse   = int(s[9] * 3.6) if s[9] is not None else None
                indicatif = (s[1] or "").strip() or "-"
                categorie = s[16] if len(s) > 16 else None
                au_sol    = 1 if s[8] else 0

                if au_sol or not est_avion_de_ligne(indicatif, vitesse, categorie):
                    filtres += 1
                    continue

                if icao not in aircraft_type_cache:
                    aircraft_type_cache[icao] = chercher_type_aeronef(icao)
                type_code = aircraft_type_cache[icao]
                if type_code is not None and not est_transport_commercial(type_code):
                    filtres += 1
                    continue

                code_infr, msg_infr = analyser_infraction(alt_m, time_s, au_sol, cfg)

                row = {
                    "date": date_s, "heure": time_s, "timestamp": now_ts,
                    "icao24": icao, "indicatif": indicatif,
                    "altitude_m":   alt_m,
                    "altitude_geo": int(s[13]) if s[13] is not None else None,
                    "vitesse_kmh":  vitesse,
                    "cap_deg":      int(s[10]) if s[10] is not None else None,
                    "au_sol": au_sol, "pays": s[2] or "-",
                    "lat": s[6], "lon": s[5], "infraction": msg_infr,
                }

                if icao in active_flights:
                    flight = active_flights[icao]
                    flight["last_seen"] = now_ts
                    if flight["has_infraction"]:
                        frozen += 1
                    else:
                        update_passage(flight["id"], row)
                        flight["has_infraction"] = bool(code_infr)
                        if code_infr:
                            n_infr += 1
                        updated += 1
                else:
                    if code_infr:
                        n_infr += 1
                    db_id = save_passage(row)
                    active_flights[icao] = {
                        "id":             db_id,
                        "has_infraction": bool(code_infr),
                        "last_seen":      now_ts,
                    }
                    added += 1

            cutoff         = now_ts - config.DEDUP_WINDOW
            active_flights = {k: v for k, v in active_flights.items()
                              if v["last_seen"] >= cutoff}

            with self.lock:
                self.state["active_flights"]      = active_flights
                self.state["aircraft_type_cache"] = aircraft_type_cache
                self.state["last_scan"]  = time_s
                self.state["added"]      = added
                self.state["updated"]    = updated
                self.state["frozen"]     = frozen
                self.state["filtres"]    = filtres
                self.state["n_infr"]     = n_infr
                self.state["status_ok"]  = True
                self.state["scan_count"] += 1
                sc = self.state["scan_count"]
                infr_txt = f" · ⚠ {n_infr} infraction(s)" if n_infr else ""

                # Résumé de l'interruption précédente si applicable
                recovery_txt = ""
                if self.state["error_count"] > 0:
                    n_missed  = self.state["error_count"]
                    err_since = self.state["error_since"]
                    duree_min = int((now - err_since).total_seconds() / 60) if err_since else 0
                    label = "limite de requêtes" if self.state["last_error_type"] == "rate_limit" else "erreur réseau"
                    recovery_txt = f" · ⚠ Reprise après {n_missed} scan(s) manqué(s) ({duree_min} min — {label})"
                    self.state["error_count"]     = 0
                    self.state["error_since"]     = None
                    self.state["last_error_type"] = None

                self.state["status"] = (
                    f"Scan #{sc} à {time_s} · {added} nouveau(x) · "
                    f"{updated} mis à jour · {frozen} figé(s) · {filtres} filtré(s)"
                    + infr_txt + recovery_txt)

        except Exception as e:
            import requests as _req
            if isinstance(e, _req.exceptions.HTTPError) and e.response is not None and e.response.status_code == 429:
                err_type = "rate_limit"
                err_msg  = "Trop de requêtes OpenSky (429) — scan ignoré"
            else:
                err_type = "error"
                err_msg  = f"Erreur scan : {e}"
            with self.lock:
                if self.state["error_count"] == 0:
                    self.state["error_since"] = datetime.now()
                self.state["error_count"]    += 1
                self.state["last_error_type"] = err_type
                self.state["status"]          = err_msg
                self.state["status_ok"]       = False

    def get_state(self):
        with self.lock:
            return dict(self.state)

    def clear_flights(self):
        with self.lock:
            self.state["active_flights"] = {}
