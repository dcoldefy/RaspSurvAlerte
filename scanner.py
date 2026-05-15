"""
Thread de scan — interroge OpenSky ou FlightRadar24 toutes les 60 s,
maintient l'état partagé accessible par Flask.
"""
import threading
import time
import requests
from datetime import datetime

CACHE_TTL = 7 * 24 * 3600  # 7 jours en secondes

import config
from database import save_passage, update_passage, get_active_flights, init_db
from filters import est_avion_de_ligne, est_transport_commercial, analyser_infraction
from api import chercher_type_aeronef
from utils import distance_km


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
            "retry_until":         None,
            "opensky_credits":     None,
        }
        self._stop = threading.Event()

    def start(self):
        init_db()
        with self.lock:
            self.state["active_flights"] = get_active_flights()
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        backoff = 0
        while not self._stop.is_set():
            self._do_scan()
            with self.lock:
                retry_after = self.state.pop("retry_after", None)
                is_rate_limit = (
                    not self.state["status_ok"]
                    and self.state["last_error_type"] == "rate_limit"
                )
            if retry_after:
                backoff = 0
                wait = retry_after
            elif is_rate_limit:
                backoff = min(backoff + 300, 1800)
                wait = config.SCAN_INTERVAL + backoff
            else:
                backoff = 0
                wait = config.SCAN_INTERVAL
            if is_rate_limit or retry_after:
                with self.lock:
                    self.state["retry_until"] = time.time() + wait
            self._stop.wait(wait)

    # ------------------------------------------------------------------
    # Récupération des données — retourne (states, credits_remaining)
    # states = liste de dicts normalisés
    # ------------------------------------------------------------------

    def _fetch_opensky(self, cfg):
        """Interroge OpenSky, retourne (states, credits_remaining)."""
        delta = max(cfg["rayon_km"], 1) / 111.0
        lat, lon = cfg["lat"], cfg["lon"]
        url = (f"https://opensky-network.org/api/states/all"
               f"?lamin={lat-delta}&lomin={lon-delta}"
               f"&lamax={lat+delta}&lomax={lon+delta}")

        auth = (cfg["opensky_user"], cfg["opensky_pass"]) \
               if cfg.get("opensky_user") and cfg.get("opensky_pass") else None
        resp = requests.get(url, timeout=15, auth=auth)
        rl_headers = {k: v for k, v in resp.headers.items()
                      if 'rate' in k.lower() or 'limit' in k.lower()}
        if rl_headers:
            import logging
            logging.getLogger(__name__).info("OpenSky rate-limit headers: %s", rl_headers)
        credits_remaining = resp.headers.get("X-Rate-Limit-Remaining")
        resp.raise_for_status()

        raw = [s for s in (resp.json().get("states") or [])
               if s[5] is not None and s[6] is not None
               and distance_km(lat, lon, s[6], s[5]) <= cfg["rayon_km"]]

        states = []
        for s in raw:
            states.append({
                "icao":        (s[0] or "").strip(),
                "indicatif":   (s[1] or "").strip() or "-",
                "pays":        s[2] or "-",
                "lat":         s[6],
                "lon":         s[5],
                "alt_m":       int(s[7])       if s[7] is not None else None,
                "alt_geo":     int(s[13])      if s[13] is not None else None,
                "vitesse":     int(s[9] * 3.6) if s[9] is not None else None,
                "cap":         int(s[10])      if s[10] is not None else None,
                "au_sol":      1 if s[8] else 0,
                "categorie":   s[16] if len(s) > 16 else None,
            })
        return states, credits_remaining

    def _fetch_flightradar24(self, cfg):
        """Interroge FlightRadar24, retourne (states, None)."""
        from FlightRadar24 import FlightRadar24API
        fr = FlightRadar24API()
        bounds = fr.get_bounds_by_point(cfg["lat"], cfg["lon"],
                                        cfg["rayon_km"] * 1000)
        flights = fr.get_flights(bounds=bounds)

        states = []
        for f in flights:
            icao = (f.id or "").strip()
            if not icao:
                continue
            # FR24 : altitude en pieds, vitesse en nœuds
            alt_m   = int(f.altitude * 0.3048) if f.altitude else None
            vitesse = int(f.ground_speed * 1.852) if f.ground_speed else None
            states.append({
                "icao":        icao,
                "indicatif":   (f.callsign or "").strip() or "-",
                "pays":        "-",
                "lat":         f.latitude,
                "lon":         f.longitude,
                "alt_m":       alt_m,
                "alt_geo":     alt_m,
                "vitesse":     vitesse,
                "cap":         int(f.heading) if f.heading else None,
                "au_sol":      1 if f.on_ground else 0,
                "categorie":   None,
            })
        return states, None

    # ------------------------------------------------------------------
    # Scan principal
    # ------------------------------------------------------------------

    def _do_scan(self):
        cfg = config.load()
        source = cfg.get("source", "flightradar24")
        with self.lock:
            self.state["status"]    = "Scan en cours..."
            self.state["status_ok"] = True

        credits_remaining = None
        try:
            if source == "opensky":
                states, credits_remaining = self._fetch_opensky(cfg)
            else:
                states, credits_remaining = self._fetch_flightradar24(cfg)

            now    = datetime.now()
            now_ts = int(now.timestamp())
            date_s = now.strftime("%d/%m/%Y")
            time_s = now.strftime("%H:%M:%S")

            added = updated = frozen = filtres = n_infr = 0

            with self.lock:
                active_flights      = dict(self.state["active_flights"])
                aircraft_type_cache = dict(self.state["aircraft_type_cache"])

            for s in states:
                icao = s["icao"]
                if not icao:
                    continue

                alt_m       = s["alt_m"]
                vitesse     = s["vitesse"]
                indicatif   = s["indicatif"]
                categorie   = s["categorie"]
                au_sol      = s["au_sol"]

                if alt_m is not None and alt_m > cfg.get("alt_max_scan", 8000):
                    filtres += 1
                    continue

                if au_sol or not est_avion_de_ligne(indicatif, vitesse, categorie, cfg.get("prefixes_exclus", [])):
                    filtres += 1
                    continue

                cached = aircraft_type_cache.get(icao)
                if cached is None or (now_ts - cached["ts"]) > CACHE_TTL:
                    aircraft_type_cache[icao] = {"type": chercher_type_aeronef(icao), "ts": now_ts}
                type_code = aircraft_type_cache[icao]["type"]
                if type_code is not None and not est_transport_commercial(type_code):
                    filtres += 1
                    continue

                code_infr, msg_infr = analyser_infraction(alt_m, time_s, au_sol, cfg)

                row = {
                    "date": date_s, "heure": time_s, "timestamp": now_ts,
                    "icao24":       icao,
                    "indicatif":    indicatif,
                    "altitude_m":   alt_m,
                    "altitude_geo": s["alt_geo"],
                    "vitesse_kmh":  vitesse,
                    "cap_deg":      s["cap"],
                    "au_sol":       au_sol,
                    "pays":         s["pays"],
                    "lat":          s["lat"],
                    "lon":          s["lon"],
                    "infraction":   msg_infr,
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

            cache_cutoff        = now_ts - CACHE_TTL
            aircraft_type_cache = {k: v for k, v in aircraft_type_cache.items()
                                   if v["ts"] >= cache_cutoff}

            with self.lock:
                self.state["active_flights"]      = active_flights
                self.state["aircraft_type_cache"] = aircraft_type_cache
                self.state["last_scan"]    = time_s
                self.state["added"]        = added
                self.state["updated"]      = updated
                self.state["frozen"]       = frozen
                self.state["filtres"]      = filtres
                self.state["n_infr"]       = n_infr
                self.state["status_ok"]    = True
                self.state["retry_until"]  = None
                self.state["opensky_credits"] = int(credits_remaining) if credits_remaining is not None else None
                self.state["scan_count"] += 1
                sc = self.state["scan_count"]
                infr_txt = f" · ⚠ {n_infr} infraction(s)" if n_infr else ""

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

                src_lbl = "FR24" if source == "flightradar24" else "OpenSky"
                self.state["status"] = (
                    f"[{src_lbl}] Scan #{sc} à {time_s} · {added} nouveau(x) · "
                    f"{updated} mis à jour · {frozen} figé(s) · {filtres} filtré(s)"
                    + infr_txt + recovery_txt)

        except Exception as e:
            if source == "opensky":
                import requests as _req
                if isinstance(e, _req.exceptions.HTTPError) and e.response is not None and e.response.status_code == 429:
                    err_type    = "rate_limit"
                    retry_after = (e.response.headers.get("X-Rate-Limit-Retry-After-Seconds")
                                   or e.response.headers.get("Retry-After"))
                    try:
                        retry_after = int(retry_after)
                    except (TypeError, ValueError):
                        retry_after = None
                    err_msg = "Trop de requêtes OpenSky (429)"
                else:
                    err_type    = "error"
                    retry_after = None
                    err_msg     = f"Erreur scan OpenSky : {e}"
            else:
                err_type    = "error"
                retry_after = None
                err_msg     = f"Erreur scan FR24 : {e}"

            with self.lock:
                if self.state["error_count"] == 0:
                    self.state["error_since"] = datetime.now()
                self.state["error_count"]    += 1
                self.state["last_error_type"] = err_type
                self.state["status"]          = err_msg
                self.state["status_ok"]       = False
                if err_type == "rate_limit" and retry_after:
                    self.state["retry_after"] = retry_after

    def stop(self):
        self._stop.set()

    def get_state(self):
        with self.lock:
            return dict(self.state)

    def clear_flights(self):
        with self.lock:
            self.state["active_flights"] = {}
