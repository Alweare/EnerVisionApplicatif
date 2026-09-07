# Module `prediction` — Prédiction de pics de consommation

Suivi d'implémentation. À lire avant de reprendre EN-38 (extraction) ou EN-39
(entraînement).

---

## 1. Où on en est

| Ticket | Sujet | État |
|---|---|---|
| **EN-37** | Feature engineering séries temporelles | **Fait** (ce document) |
| EN-38 | Extraction / assemblage du jeu de données | À faire — `get_measurements()` déjà écrit ici |
| EN-39 | Entraînement + évaluation du modèle | À faire |

## 2. Le pipeline ML, vue d'ensemble

Une régression linéaire apprend `consommation ≈ a·f1 + b·f2 + c·f3 + d` à partir
d'exemples passés. Il lui faut, pour chaque exemple :

- **X** — les *features* : `lag_1h`, `lag_24h`, `rolling_mean_24h`
- **y** — la *cible* : `consumption_kw` à cet instant

L'historique brut en base est une simple série chronologique ; une régression
n'a aucune mémoire d'une ligne à l'autre. EN-37 transforme cette série en un
tableau où **chaque ligne se suffit à elle-même**.

```
EN-37 (ici)                     EN-38 / EN-39
─────────────────────────       ─────────────────────────────────────
get_measurements()          →   1. get_measurements() + add_time_features()
  SELECT ... FROM measurement   2. df.dropna(subset=[*features, cible])
add_time_features(df)           3. X = df[[lag_1h, lag_24h, rolling_mean_24h]]
  + lag_1h, lag_24h,               y = df["consumption_kw"]
    rolling_mean_24h            4. model.fit(X, y) → évaluation → sauvegarde
                                Plus tard : model.predict() sur features
                                fraîches ; si > seuil du site → alerte "pic"
```

EN-37 **ne fait aucun entraînement** : il prépare la matière première.

## 3. Fichiers livrés

| Fichier | Rôle |
|---|---|
| `features/time_features.py` | `add_time_features(df)` — fonction **pure**, zéro I/O |
| `repository/measurement_repository.py` | `get_measurements(site_id=None)` — extraction SQL, renvoie un `DataFrame` |
| `tests/test_time_features.py` | Les 4 critères d'acceptation + la neutralisation |
| `tests/test_measurement_repository.py` | La requête SQL (mockée) |
| `tests/conftest.py` | Variables d'env Postgres factices (collecte des tests sans base) |
| `backend/requirements.txt` | +`pandas` |

## 4. Décisions prises et pourquoi (le cheminement)

### 4.1 Décalage par nombre de lignes, pas par temps

L'ETL tourne toutes les 60 s → **1 mesure/minute**. Donc « il y a 1 h » =
`shift(60)`, « il y a 24 h » = `shift(1440)` (constantes `ROWS_PER_HOUR` /
`ROWS_PER_DAY`). Une mesure/heure donnerait `shift(1)` / `shift(24)` — faux ici.

**Limite connue (acceptée pour le MVP)** : si des minutes entières sont absentes
de la table (panne prolongée du pipeline), un lag « 1 h » peut correspondre à un
peu plus ou moins de 60 min réelles. Version robuste possible plus tard :
`merge_asof` / `resample` sur une grille d'une minute.

### 4.2 On ne filtre pas les lignes dégradées en SQL

Réflexe naturel : `WHERE data_quality = 'good'`. **Rejeté** : supprimer des
lignes au milieu de la série décale `shift(60)` (60 lignes en arrière ne
vaudraient plus 60 minutes). Silencieux et faux.

À la place : on récupère **toutes** les lignes + les colonnes `data_quality` et
`null_reason`, et on neutralise en pandas (cf. 4.3).

### 4.3 Neutralisation fine via `null_reason`

L'ETL remplace **toute** valeur `null` par la précédente (forward-fill), sans
distinction. `null_reason` est le marqueur laissé sur la ligne : il dit quels
champs étaient absents en brut, donc si la `consumption_kw` stockée est une vraie
mesure ou une recopie.

| `null_reason` | `consumption_kw` |
|---|---|
| `consumption_sensor_failure` | recopiée → **neutralisée** (`NaN`) |
| `network_loss` | recopiée → **neutralisée** (`NaN`) |
| `electrical_sensor_failure` | réelle (seuls tension / courant / cos φ manquent) → gardée |
| `temperature_sensor_failure` | réelle → gardée |
| `None` | lecture complète → gardée |

→ `CONSUMPTION_TAINTING_REASONS = {"consumption_sensor_failure", "network_loss"}`.

**La ligne est conservée** (pas supprimée), seule la **valeur** passe à `NaN` :
on garde le placeholder pour ne pas décaler le comptage des lags. Un lag qui
retombe sur une ligne neutralisée vaut `NaN`.

C'est un filtre volontairement conservateur mais simple. Si on perd trop de
lignes, on pourra affiner (p. ex. ne neutraliser que si la conso elle-même
était `null`).

### 4.4 `shift(1)` AVANT `rolling` — le point de revue n°1

```python
grouped.transform(lambda s: s.shift(1).rolling(window=ROWS_PER_DAY, min_periods=1).mean())
```

Sans le `shift(1)`, la moyenne glissante inclurait `consumption_kw[T]` —
c'est-à-dire **la cible elle-même**. Le modèle aurait la réponse cachée dans ses
features : excellent en test, inutilisable en production où cette valeur future
n'existe pas encore. C'est une **fuite de données**.

Règle générale du module : une feature de la ligne T n'utilise **que** du passé
strictement avant T.

`min_periods=1` : `rolling_mean_24h` existe dès qu'il y a une valeur passée
(calculée sur moins de points au début), contrairement aux lags.

### 4.5 Les `NaN` sont laissés tels quels

Le ticket interdit de remplir un lag manquant par `0` ou la moyenne globale
(biais silencieux). `NaN` = « inconnu », honnête. Ces lignes sont retirées par un
`df.dropna(...)` **au moment du `.fit()`** (EN-39), jamais avant — et jamais
rebouchées.

Conséquence avec peu de données : `lag_24h` a besoin de 1440 lignes en amont, donc
au début presque toutes les lignes sont `NaN` → peu ou zéro ligne entraînable.
Ce n'est pas un bug, c'est le signal « pas encore assez d'historique ».

### 4.6 Calcul par site

Tous les `shift` / `rolling` passent par `df.groupby("site_id")` : les séries
temporelles de deux sites ne sont **jamais** mélangées. Les premières lignes d'un
site valent `NaN`, jamais une valeur tirée d'un autre site.

## 5. Critères d'acceptation → tests

| Critère (EN-37) | Test |
|---|---|
| Lags par `site_id`, jamais mélangés | `test_lags_are_computed_per_site_and_never_mixed` |
| Lags `null` si historique insuffisant | `test_lags_are_null_when_history_is_insufficient` |
| `shift()` avant `rolling()` | `test_rolling_mean_shifts_before_rolling_and_excludes_current_row` |
| Aucune fuite de données (feature T ⟂ conso T) | `test_no_data_leakage_from_current_row` |
| (bonus) neutralisation `null_reason` | `test_tainted_consumption_is_neutralized_but_row_is_kept` |

Tous les tests tournent sur des `DataFrame` synthétiques — **aucune base réelle
nécessaire** pour ce ticket.

## 6. Lancer les tests

```bash
# depuis la racine du repo, venv activé
python -m pytest backend/prediction/tests --cov=backend/prediction --cov-report=term-missing --cov-fail-under=80
```

État actuel : `10 passed`, couverture `100 %` (seuil CI : 80 %).

La CI ([.github/workflows/ci-cd.yml](../../.github/workflows/ci-cd.yml)) lance
chaque service isolément avec un `PYTHONPATH` dédié. Lancer `pytest backend` en
entier échoue à la collecte (collision SQLAlchemy `etl` + `core` sur
`ener.measurement`) — c'est **pré-existant** et sans rapport avec ce module.

## 7. Pour EN-38 / EN-39

- `get_measurements()` est prêt : renvoie `site_id, measurement_date,
  consumption_kw, data_quality, null_reason`, trié par site puis date croissante.
- Enchaînement attendu :
  ```python
  df = add_time_features(get_measurements())
  df = df.dropna(subset=["lag_1h", "lag_24h", "rolling_mean_24h", "consumption_kw"])
  X = df[["lag_1h", "lag_24h", "rolling_mean_24h"]]
  y = df["consumption_kw"]
  ```
- `data_quality` / `null_reason` sont conservés en sortie de `add_time_features`
  pour qu'EN-39 puisse aussi exclure les lignes dégradées **comme cible** sans
  refaire une requête.
- La cible est ici `consumption_kw` à l'instant T (prédiction du « maintenant »
  à partir du passé récent). Pour un vrai horizon de prévision (T+1h, T+24h), il
  faudra décaler la cible — à décider en EN-39.

## 8. Note : refactor `core` → `shared`

Un merge de `develop` pendant l'implémentation a déplacé `core/database.py` →
`shared/database.py` (et `core/base.py` → `shared/base.py`). L'import du
repository a été mis à jour en conséquence (`from shared.database import
engine`).
