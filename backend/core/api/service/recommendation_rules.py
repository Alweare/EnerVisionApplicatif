"""Catalogue de règles de recommandation, en dur (EN-258).

Chaque règle regarde une prédiction de consommation et le site associé, et
décide si elle doit produire une recommandation. Les règles sont volontairement
en code (et non en base) : pures, versionnées, testables sans base de données.

Ajouter une règle = ajouter une entrée à `RULES`. Le `key` sert d'identifiant
stable (traçabilité + idempotence côté moteur), il ne doit jamais changer une
fois livré.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

_JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


class _Prediction(Protocol):
    predicted_for: object
    predicted_consumption_kw: float | None


class _Site(Protocol):
    capacity_kw: float | None


@dataclass(frozen=True)
class Rule:
    key: str
    action_type: str
    matches: Callable[[_Prediction, _Site], bool]
    # Reçoit aussi l'instant de référence : le message est figé en base, il doit
    # donc dater les échéances autrement qu'en « demain » (qui pourrirait).
    message: Callable[[_Prediction, _Site, datetime], str]
    # Gain estimé en kW (ex. charge à délester), ou None si non chiffrable.
    estimated_gain_kw: Callable[[_Prediction, _Site], float | None]


def describe_deadline(predicted_for: datetime, now: datetime) -> str:
    """Échéance d'un pic, en français, relative à `now`.

    « à 18h00 » quand c'est le jour même (comportement historique), sinon on
    ajoute le jour en clair — « mardi 09/09 à 18h00 » — parce que le message est
    stocké tel quel : une formulation relative (« demain ») deviendrait fausse
    dès le lendemain. Utile dès que la prédiction couvre T+24h / T+1 semaine.
    """
    heure = f"{predicted_for:%Hh%M}"
    if predicted_for.date() == now.date():
        return f"à {heure}"
    return f"{_JOURS[predicted_for.weekday()]} {predicted_for:%d/%m} à {heure}"


def capacity_ratio(prediction: _Prediction, site: _Site) -> float | None:
    """Part de la capacité du site couverte par la conso prédite, ou None si non calculable."""
    if (
        not site.capacity_kw
        or prediction.predicted_consumption_kw is None
        or prediction.predicted_for is None
    ):
        return None
    return prediction.predicted_consumption_kw / site.capacity_kw


RULES: list[Rule] = [
    Rule(
        key="peak_over_capacity",
        action_type="reduce_load",
        matches=lambda p, s: (r := capacity_ratio(p, s)) is not None and r > 1.0,
        message=lambda p, s, now: (
            f"Dépassement de capacité prévu {describe_deadline(p.predicted_for, now)} : "
            f"{p.predicted_consumption_kw:.0f} kW pour {s.capacity_kw:.0f} kW installés. "
            f"Délester la charge non critique avant cette plage."
        ),
        estimated_gain_kw=lambda p, s: round(
            p.predicted_consumption_kw - s.capacity_kw, 1
        ),
    ),
    Rule(
        key="peak_over_90pct_capacity",
        action_type="shift_load",
        matches=lambda p, s: (r := capacity_ratio(p, s)) is not None and 0.9 <= r <= 1.0,
        message=lambda p, s, now: (
            f"Pic prévu {describe_deadline(p.predicted_for, now)} : "
            f"{p.predicted_consumption_kw:.0f} kW "
            f"(≈{capacity_ratio(p, s) * 100:.0f} % de la capacité). "
            f"Décaler les usages flexibles hors de cette plage."
        ),
        estimated_gain_kw=lambda p, s: None,
    ),
]


def evaluate(prediction: _Prediction, site: _Site) -> list[Rule]:
    """Règles déclenchées par cette prédiction, dans l'ordre du catalogue."""
    return [rule for rule in RULES if rule.matches(prediction, site)]
