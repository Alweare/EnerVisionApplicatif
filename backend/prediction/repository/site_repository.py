"""
Liste des sites pour lesquels le scheduler doit générer un forecast.

Même style que `measurement_repository.py` (SQL brut + `pd.read_sql` via
`shared.database.engine`, pas d'ORM) : le module `prediction` n'a jamais eu
de couche ORM, inutile d'en introduire une pour une seule requête de lecture.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from shared.database import engine as default_engine

# `status = 'active'` : même convention que backend/core
# (api/repository/site_repository.py, `Site.status == "active"`).
_ACTIVE_SITES_QUERY = """
    SELECT site_id
    FROM ener.site
    WHERE status = 'active'
    ORDER BY site_id
"""


def get_active_site_ids(engine: Engine = default_engine) -> list[str]:
    """Identifiants des sites actifs, pour lesquels le scheduler doit
    générer un forecast. Jamais de liste codée en dur : `ener.site` reste la
    seule source de vérité."""
    df = pd.read_sql(text(_ACTIVE_SITES_QUERY), engine)
    return df["site_id"].tolist()
