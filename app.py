"""Interface Streamlit : présente les retours de l'API TMDB et la base SQLite."""
import os
import sqlite3
import time

import pandas as pd
import requests
import streamlit as st
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True), override=True)
CLE = os.environ.get("TMDB_API_KEY")
BASE = "https://api.themoviedb.org/3"

CODES_A_REESSAYER = {429, 500, 502, 503, 504}
MESSAGES = {
    400: "Requête invalide (400).",
    401: "Non autorisé (401) : clé API absente ou invalide.",
    403: "Accès interdit (403).",
    404: "Introuvable (404) : identifiant inconnu.",
}


def appeler_api(url, params=None, essais=4, pause=1.0):
    """GET robuste (Q1). Renvoie le JSON, None si 404, lève une erreur sinon."""
    for tentative in range(1, essais + 1):
        try:
            rep = requests.get(url, params=params, timeout=10)
        except (requests.ConnectionError, requests.Timeout):
            attente = pause * 2 ** (tentative - 1)
        else:
            if rep.ok:
                return rep.json()
            if rep.status_code == 404:
                return None
            if rep.status_code not in CODES_A_REESSAYER:
                raise RuntimeError(MESSAGES.get(rep.status_code, f"Erreur HTTP {rep.status_code}"))
            retry_after = rep.headers.get("Retry-After", "")
            attente = float(retry_after) if retry_after.isdigit() else pause * 2 ** (tentative - 1)
        if tentative < essais:
            time.sleep(attente)
    raise RuntimeError(f"Échec après {essais} tentatives")


@st.cache_data(ttl=3600)          # Q3 : cache d'1 heure, par id de film
def get_movie_details(movie_id):
    data = appeler_api(f"{BASE}/movie/{movie_id}", params={"api_key": CLE})
    if data is None:
        return None
    return {
        "Titre": data["title"],
        "Date de sortie": data["release_date"],
        "Genres": ", ".join(g["name"] for g in data["genres"]),
        "Popularité": data["popularity"],
        "Note moyenne": data["vote_average"],
    }


@st.cache_data(ttl=3600)
def lire_base(requete, parametres=()):
    """Lit tmdb.db en lecture seule."""
    con = sqlite3.connect("file:tmdb.db?mode=ro", uri=True)
    try:
        return pd.read_sql(requete, con, params=parametres)
    finally:
        con.close()


st.set_page_config(page_title="API TMDB", page_icon="🎬")
st.title("🎬 API TMDB")
onglet1, onglet2 = st.tabs(["Détails d'un film", "Base TMDB"])

with onglet1:
    if not CLE:
        st.error("TMDB_API_KEY introuvable : vérifie le fichier .env.")
    else:
        movie_id = st.number_input("Identifiant TMDB du film", min_value=1, value=550, step=1)
        if st.button("Chercher"):
            try:
                film = get_movie_details(int(movie_id))
            except RuntimeError as e:
                st.error(str(e))
            else:
                if film is None:
                    st.warning("Aucun film avec cet identifiant.")
                else:
                    st.subheader(film["Titre"])
                    col1, col2 = st.columns(2)
                    col1.metric("Popularité", film["Popularité"])
                    col2.metric("Note moyenne", film["Note moyenne"])
                    st.write(f"**Sortie :** {film['Date de sortie']}")
                    st.write(f"**Genres :** {film['Genres']}")

with onglet2:
    if not os.path.exists("tmdb.db"):
        st.warning("tmdb.db introuvable : lance d'abord le notebook ou update_tmdb.py.")
    else:
        total = lire_base("SELECT count(*) AS n FROM movies")["n"][0]
        st.write(f"**{total:,}** films en base".replace(",", " "))
        recherche = st.text_input("Rechercher un titre")
        if recherche:
            df = lire_base(
                "SELECT id, original_title, popularity FROM movies "
                "WHERE original_title LIKE ? ORDER BY popularity DESC LIMIT 50",
                (f"%{recherche}%",),
            )
        else:
            df = lire_base("SELECT id, original_title, popularity FROM movies "
                           "ORDER BY popularity DESC LIMIT 20")
        st.dataframe(df, use_container_width=True, hide_index=True)