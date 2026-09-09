from datetime import datetime
from types import SimpleNamespace

import pytest

from core.api.service import recommendation_rules


def _prediction(kw: float | None, when: datetime | None = datetime(2026, 9, 8, 18, 0)):
    return SimpleNamespace(predicted_consumption_kw=kw, predicted_for=when)


def _site(capacity_kw: float | None):
    return SimpleNamespace(capacity_kw=capacity_kw)


def _keys(prediction, site) -> list[str]:
    return [rule.key for rule in recommendation_rules.evaluate(prediction, site)]


def test_no_rule_below_90_percent():
    assert _keys(_prediction(150), _site(200)) == []


def test_shift_load_between_90_and_100_percent():
    assert _keys(_prediction(190), _site(200)) == ["peak_over_90pct_capacity"]


def test_reduce_load_above_capacity():
    assert _keys(_prediction(220), _site(200)) == ["peak_over_capacity"]


def test_exactly_at_capacity_is_shift_load():
    assert _keys(_prediction(200), _site(200)) == ["peak_over_90pct_capacity"]


@pytest.mark.parametrize(
    "prediction, site",
    [
        (_prediction(None), _site(200)),
        (_prediction(500), _site(None)),
        (_prediction(500), _site(0)),
        (_prediction(500, when=None), _site(200)),
    ],
)
def test_non_scorable_predictions_yield_nothing(prediction, site):
    assert _keys(prediction, site) == []


_NOW = datetime(2026, 9, 8, 12, 0)  # même jour que le `when` par défaut


def test_message_mentions_hour_and_values():
    rule = recommendation_rules.evaluate(_prediction(220), _site(200))[0]
    message = rule.message(_prediction(220), _site(200), _NOW)
    assert "18h00" in message
    assert "220" in message
    assert "200" in message


# --- describe_deadline -----------------------------------------------

def test_deadline_same_day_keeps_the_historical_wording():
    when = datetime(2026, 9, 8, 18, 0)
    assert recommendation_rules.describe_deadline(when, _NOW) == "à 18h00"


def test_deadline_other_day_spells_out_the_date():
    when = datetime(2026, 9, 15, 18, 0)  # mardi, une semaine plus tard
    assert recommendation_rules.describe_deadline(when, _NOW) == "mardi 15/09 à 18h00"


def test_message_dates_a_next_day_peak():
    tomorrow = _prediction(220, when=datetime(2026, 9, 9, 8, 30))
    rule = recommendation_rules.evaluate(tomorrow, _site(200))[0]
    message = rule.message(tomorrow, _site(200), _NOW)
    assert "mercredi 09/09 à 08h30" in message
