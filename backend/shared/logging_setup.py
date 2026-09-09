"""Logs structurés en JSON, partagés par core, etl et workeringestion.

Une ligne de log = un objet JSON. Loki peut alors filtrer sur des champs
(`| json | status >= 500`) au lieu de chercher du texte à la regex, ce qui
évite les faux positifs — un numéro de port à quatre chiffres ressemble à un
code HTTP quand on ne lit que du texte.
"""

import json
import logging
import os
from datetime import datetime, timezone


_ATTRIBUTS_STANDARD = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for cle, valeur in record.__dict__.items():
            if cle not in _ATTRIBUTS_STANDARD and not cle.startswith("_"):
                log[cle] = valeur

        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)

        return json.dumps(log, ensure_ascii=False, default=str)


def setup_logging(service: str) -> None:
    """À appeler une fois au démarrage, avant tout autre log.

    `service` étiquette chaque ligne : c'est ce qui permet de distinguer core,
    etl et worker dans une même requête Loki.
    """
    niveau = os.environ.get("LOG_LEVEL", "INFO").upper()

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    racine = logging.getLogger()
    racine.handlers.clear()  
    racine.addHandler(handler)
    racine.setLevel(niveau)

    ancienne_fabrique = logging.getLogRecordFactory()

    def fabrique(*args, **kwargs):
        record = ancienne_fabrique(*args, **kwargs)
        record.service = service
        return record

    logging.setLogRecordFactory(fabrique)
