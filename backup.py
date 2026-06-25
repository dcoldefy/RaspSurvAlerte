"""
Sauvegarde automatique de survalerte.db vers une clé USB.
Peut être lancé manuellement ou via le timer systemd survalerte-backup.timer.

Usage : python3 backup.py [--path /chemin/custom]
"""
import argparse
import glob
import os
import shutil
import sys
from datetime import datetime

import config

BACKUP_FILENAME = "survalerte_{date}.db"
MAX_BACKUPS     = 7   # nombre de sauvegardes à conserver


def find_usb_path():
    """Cherche un répertoire de sauvegarde USB monté."""
    custom = config.load().get("backup_usb_path", "").strip()
    if custom and os.path.isdir(custom):
        return custom

    # Auto-détection : /media/<user>/*/ ou /media/*/
    patterns = [
        f"/media/{os.environ.get('USER', 'david')}/*/",
        "/media/*/",
        "/mnt/*/",
    ]
    for pattern in patterns:
        for path in glob.glob(pattern):
            if os.path.ismount(path) and os.access(path, os.W_OK):
                return path.rstrip("/")
    return None


def run_backup(usb_path=None):
    db_src = config.DB_FILE
    if not os.path.exists(db_src):
        return False, f"Base introuvable : {db_src}"

    dest_dir = usb_path or find_usb_path()
    if not dest_dir:
        return False, "Aucune clé USB montée et aucun chemin configuré"

    os.makedirs(dest_dir, exist_ok=True)

    date_str  = datetime.now().strftime("%Y-%m-%d")
    dest_file = os.path.join(dest_dir, BACKUP_FILENAME.format(date=date_str))

    shutil.copy2(db_src, dest_file)

    # Conserver seulement les MAX_BACKUPS plus récentes
    backups = sorted(glob.glob(os.path.join(dest_dir, "survalerte_*.db")))
    for old in backups[:-MAX_BACKUPS]:
        try:
            os.remove(old)
        except OSError:
            pass

    size_kb = os.path.getsize(dest_file) // 1024
    return True, f"Sauvegarde OK → {dest_file} ({size_kb} Ko)"


def save_last_status(ok, msg):
    """Écrit le résultat dans un fichier d'état lisible par Flask."""
    status_file = os.path.expanduser("~/.survalerte/backup_status.txt")
    os.makedirs(os.path.dirname(status_file), exist_ok=True)
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    with open(status_file, "w") as f:
        f.write(f"{'OK' if ok else 'ERR'}|{ts}|{msg}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", help="Chemin de sauvegarde (remplace l'auto-détection)")
    args = parser.parse_args()

    ok, msg = run_backup(args.path)
    save_last_status(ok, msg)
    print(msg)
    sys.exit(0 if ok else 1)
