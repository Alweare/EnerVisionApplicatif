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


# Emplacement du fichier de battement. Défaut dans le répertoire personnel du
# compte qui exécute le service (non accessible en écriture par d'autres
# utilisateurs), plutôt qu'un répertoire public partagé type /tmp où un tiers
# pourrait pré-créer ou remplacer le fichier. Le service et le healthcheck
# tournant sous le même compte, ils calculent le même chemin. Surchargé par
# HEARTBEAT_FILE (docker-compose).
CHEMIN = pathlib.Path(
    os.environ.get("HEARTBEAT_FILE", str(pathlib.Path.home() / ".enervision_heartbeat"))
)


def touch() -> None:
    CHEMIN.write_text(str(time.time()))


def est_frais(age_max_secondes: float) -> bool:
    try:
        return (time.time() - CHEMIN.stat().st_mtime) < age_max_secondes
    except FileNotFoundError:
        return False
