# -*- coding: utf-8 -*-
"""
Test automatique de l'API PigeonManager (backend Django local).

Usage (avec le serveur lance : python manage.py runserver) :
    python test_dashboard.py                 # utilisateur "admin", mot de passe demande (masque)
    python test_dashboard.py admin           # utilisateur explicite, mot de passe demande
    python test_dashboard.py admin monmdp    # tout en ligne de commande

Ce que le script teste :
  1. POST /api/token/              -> recuperation du token JWT
  2. GET  /api/dashboard/stats/    -> statistiques du dashboard
  3. GET  .../activites/?limit=5   -> dernieres activites (plusieurs chemins essayes)

Aucune dependance : uniquement la bibliotheque standard Python 3.
Le serveur cible peut etre change via la variable d'environnement PM_BASE.
"""
import getpass
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("PM_BASE", "http://127.0.0.1:8000").rstrip("/")

STATS_PATHS = ["/api/dashboard/stats/", "/api/stats/"]
ACTIVITES_PATHS = ["/api/dashboard/activites/?limit=5", "/api/activites/?limit=5"]


def req(method, path, token=None, payload=None):
    """Requete HTTP simple, renvoie (statut, corps texte)."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, ConnectionError, OSError) as e:
        print()
        print("[X] Impossible de joindre " + BASE + path)
        print("    Cause : " + str(e))
        print("    -> Verifiez que le serveur tourne : python manage.py runserver")
        sys.exit(1)


def show(label, status, body):
    """Affiche le statut et le corps JSON (ou texte) d'une reponse."""
    print()
    print("========== " + label + " -> HTTP " + str(status) + " ==========")
    try:
        parsed = json.loads(body)
        print(json.dumps(parsed, indent=2, ensure_ascii=False))
    except ValueError:
        print(body[:3000])


def try_paths(label, paths, token):
    """Essaye chaque chemin jusqu'au premier 200. Renvoie le chemin qui marche."""
    status, body, p = 0, "", paths[0]
    for p in paths:
        status, body = req("GET", p, token=token)
        if status == 200:
            show(label + " [" + p + "]", status, body)
            return p
    show(label + " (dernier chemin essaye : " + p + ")", status, body)
    return None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    username = sys.argv[1] if len(sys.argv) > 1 else "admin"
    if len(sys.argv) > 2:
        password = sys.argv[2]
    else:
        password = getpass.getpass("Mot de passe de '" + username + "' : ")

    print("Serveur cible : " + BASE)
    print("Utilisateur   : " + username)
    print()

    # 1) Token JWT
    status, body = req("POST", "/api/token/",
                       payload={"username": username, "password": password})
    if status != 200:
        show("POST /api/token/", status, body)
        print()
        print("[X] Le serveur repond mais refuse la connexion.")
        if status == 401:
            print("    -> Identifiants invalides : verifiez le mot de passe du compte '"
                  + username + "'.")
        sys.exit(1)
    try:
        token = json.loads(body).get("access")
    except ValueError:
        token = None
    if not token:
        show("POST /api/token/", status, body)
        print("[X] La reponse ne contient pas de champ 'access'.")
        sys.exit(1)
    print("[OK] Token JWT obtenu (" + str(len(token)) + " caracteres).")

    # 2) Statistiques du dashboard
    stats_path = try_paths("STATS", STATS_PATHS, token)

    # 3) Dernieres activites
    act_path = try_paths("ACTIVITES", ACTIVITES_PATHS, token)

    print()
    if stats_path and act_path:
        print("[OK] Tout fonctionne. Chemins confirmes :")
        print("     " + stats_path)
        print("     " + act_path)
        print("-> Collez les deux JSON affiches ci-dessus dans la conversation.")
    else:
        print("[X] Un des deux endpoints repond 404 : le chemin d'URL est a corriger.")
        print("    -> Collez la sortie ci-dessus + le contenu de apps/dashboard/urls.py.")


if __name__ == "__main__":
    main()