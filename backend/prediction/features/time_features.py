"""
Feature engineering séries temporelles pour la prédiction de pics de
consommation (EN-37).

L'historique brut est une suite de mesures dans le temps (une par minute et
par site). Une régression linéaire ne "comprend" pas le temps par elle-même :
il faut lui donner explicitement le passé récent sous forme de colonnes
numériques.

- lag_1h  : autocorrélation à court terme (la conso change rarement
  brutalement d'une heure à l'autre).
- lag_24h : saisonnalité journalière (une même heure la veille est un bon
  indicateur de l'heure actuelle).
- rolling_mean_24h : tendance récente lissée, plus stable qu'une seule mesure
  instantanée.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Cadence du pipeline ETL : une mesure par minute
# (ETLService.start_continuous_run, interval=60 s). Les lags "horaires"
# décalent donc d'un nombre de LIGNES, pas d'une seule ligne :
# 60 lignes = 1 h, 1440 lignes = 24 h. Une mesure par heure donnerait
# shift(1) / shift(24), ce qui serait faux ici.
ROWS_PER_HOUR = 60
ROWS_PER_DAY = 24 * ROWS_PER_HOUR

# L'ETL remplace toute valeur null par la précédente (forward-fill), sans
# distinction. null_reason est le marqueur laissé sur la ligne qui dit quels
# champs étaient absents de la lecture brute -- donc si la consumption_kw
# stockée est une vraie mesure ou une recopie.
#
#   consumption_sensor_failure -> consumption_kw / consumption_kwh recopiées
#   network_loss               -> toute la lecture recopiée
#   electrical_sensor_failure  -> seuls voltage_v / current_a / power_factor
#   temperature_sensor_failure -> seuls temperature_celsius / humidity_percent
#
# Seuls les deux premiers rendent consumption_kw non fiable : on neutralise
# ces valeurs pour qu'elles ne nourrissent ni un lag ni la moyenne glissante.
CONSUMPTION_TAINTING_REASONS = frozenset(
    {"consumption_sensor_failure", "network_loss"}
)


def _consumption_is_tainted(null_reason) -> bool:
    """
    True si consumption_kw de cette ligne a été recopiée par le forward-fill
    de l'ETL (donc n'est pas une observation réelle).

    null_reason est un ARRAY(String) Postgres -> liste Python, ou None quand
    la lecture était complète.
    """
    if null_reason is None:
        return False
    return any(reason in CONSUMPTION_TAINTING_REASONS for reason in null_reason)


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ajoute les features temporelles à un DataFrame de mesures.

    Colonnes attendues en entrée : site_id, measurement_date, consumption_kw,
    data_quality, null_reason.

    Colonnes ajoutées :
    - lag_1h  : consommation 60 lignes (~1 h) plus tôt, même site.
    - lag_24h : consommation 1440 lignes (~24 h) plus tôt, même site.
      Les deux valent NaN quand l'historique disponible est insuffisant --
      jamais une valeur inventée (ni 0, ni moyenne globale). Ces lignes seront
      exclues explicitement à l'étape d'entraînement, jamais biaisées
      silencieusement.
    - rolling_mean_24h : moyenne glissante sur les 1440 dernières lignes,
      décalée d'une ligne (shift AVANT rolling) pour ne jamais inclure la
      valeur du moment T que le modèle doit prédire. Sans ce shift, la
      moyenne "verrait" une information que le modèle n'aurait jamais en
      production -- fuite de données (data leakage) : excellent en test,
      inutilisable en réel.

    Prétraitement : avant tout calcul, consumption_kw est mise à NaN sur les
    lignes dont null_reason indique qu'elle a été recopiée par le forward-fill
    (consumption_sensor_failure, network_loss). La ligne est conservée, pas
    supprimée, pour ne pas décaler le comptage de lignes des lags.

    Les lags et la moyenne sont calculés par site_id : les séries temporelles
    de deux sites ne sont jamais mélangées.

    Limite connue : le décalage se fait par nombre de lignes, pas par temps
    réel écoulé. Ça suppose une cadence proche d'une mesure/minute sans trou
    important. Si des minutes entières sont absentes de la table (panne
    prolongée du pipeline malgré le rattrapage /readings), un lag "1 h" peut
    correspondre à un peu plus ou moins de 60 minutes réelles. Acceptable au
    stade MVP ; un décalage temporel réel (merge_asof / resample sur une
    grille d'une minute) serait la version robuste si nécessaire.
    """
    df = (
        df.sort_values(["site_id", "measurement_date"])
        .reset_index(drop=True)
        .copy()
    )

    # Neutralisation des consommations recopiées par forward-fill : on écrase
    # par NaN pour qu'elles ne nourrissent ni les lags ni la moyenne glissante.
    tainted = df["null_reason"].apply(_consumption_is_tainted)
    df.loc[tainted, "consumption_kw"] = np.nan

    grouped = df.groupby("site_id")["consumption_kw"]

    # shift() reste à l'intérieur de chaque groupe -> pas de fuite entre sites.
    # Historique insuffisant -> NaN.
    df["lag_1h"] = grouped.shift(ROWS_PER_HOUR)
    df["lag_24h"] = grouped.shift(ROWS_PER_DAY)

    # shift(1) AVANT rolling : la fenêtre s'arrête à T-1, elle ne voit jamais
    # la valeur à T elle-même. min_periods=1 -> la moyenne est disponible dès
    # qu'il existe au moins une valeur passée (calculée sur moins de points en
    # début d'historique), contrairement aux lags qui restent NaN.
    df["rolling_mean_24h"] = grouped.transform(
        lambda s: s.shift(1).rolling(window=ROWS_PER_DAY, min_periods=1).mean()
    )

    return df
