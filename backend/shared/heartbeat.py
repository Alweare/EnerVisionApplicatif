"""Battement de cœur sur disque, pour les services sans serveur HTTP.

L'ETL et le worker sont des boucles : il n'y a aucun port à interroger pour
savoir s'ils vont bien. Ils touchent donc un fichier à chaque cycle, et le
healthcheck Docker vérifie que ce fichier est récent.

Un processus figé (boucle bloquée, connexion réseau qui ne rend jamais la main)
laisse son conteneur « running » alors qu'il ne fait plus rien : c'est
exactement ce que ce mécanisme détecte, contrairement au simple fait que le
processus existe.
"""

import os
import pathlib
import time


CHEMIN = pathlib.Path(os.environ["HEARTBEAT_FILE"])


def touch() -> None:
    CHEMIN.write_text(str(time.time()))


def est_frais(age_max_secondes: float) -> bool:
    try:
        return (time.time() - CHEMIN.stat().st_mtime) < age_max_secondes
    except FileNotFoundError:
        return False
