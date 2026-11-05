"""Met à jour la table movies de tmdb.db avec l'export quotidien TMDB.
À lancer tous les 3 mois (voir README). Mise à jour incrémentale : rien n'est supprimé."""
import gzip
import io
import json
import sqlite3
import time
from datetime import date, datetime, timedelta

import requests

URL_EXPORT = "http://files.tmdb.org/p/exports/movie_ids_{:%m_%d_%Y}.json.gz"
BASE = "tmdb.db"


def telecharger_export(max_jours=5):
    """Télécharge l'export le plus récent (aujourd'hui, sinon les jours précédents)."""
    for retour in range(max_jours):
        jour = date.today() - timedelta(days=retour)
        for essai in range(1, 4):                       # 3 essais par jour (erreurs temporaires)
            try:
                rep = requests.get(URL_EXPORT.format(jour), timeout=60)
            except requests.RequestException as e:
                print(f"{jour} essai {essai} : {type(e).__name__}")
                time.sleep(2 ** essai)
                continue
            if rep.ok:
                return jour, rep.content
            if rep.status_code == 404:
                break                                   # pas encore publié : jour précédent
            time.sleep(2 ** essai)
    raise RuntimeError("Aucun export TMDB récupéré")


def vers_int(valeur):
    """Convertit en 0/1 ; renvoie None (NULL en base) si la valeur est absente."""
    return None if valeur is None else int(valeur)


def main():
    debut = time.time()
    jour, contenu = telecharger_export()
    with gzip.open(io.BytesIO(contenu), "rt", encoding="utf-8") as f:
        films = [json.loads(l) for l in f if l.strip()]

    con = sqlite3.connect(BASE)
    con.execute("""CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY, original_title TEXT, popularity REAL, adult INTEGER, video INTEGER)""")
    con.execute("""CREATE TABLE IF NOT EXISTS maj_log (
        date_maj TEXT, export TEXT, films_avant INTEGER, films_apres INTEGER, duree_s REAL)""")

    avant = con.execute("SELECT count(*) FROM movies").fetchone()[0]
    lignes = [(f["id"], f.get("original_title"), f.get("popularity"),
               vers_int(f.get("adult")), vers_int(f.get("video")))
              for f in films]
    # Ajoute les nouveaux films, met à jour les existants
    con.executemany("""
        INSERT INTO movies (id, original_title, popularity, adult, video) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET original_title = excluded.original_title,
            popularity = excluded.popularity, adult = excluded.adult, video = excluded.video
    """, lignes)
    apres = con.execute("SELECT count(*) FROM movies").fetchone()[0]
    duree = round(time.time() - debut, 1)
    con.execute("INSERT INTO maj_log VALUES (?, ?, ?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"), str(jour), avant, apres, duree))
    con.commit()
    con.close()
    print(f"Mise à jour terminée : export du {jour}, {avant} -> {apres} films ({apres - avant:+d}) en {duree} s")


if __name__ == "__main__":
    main()