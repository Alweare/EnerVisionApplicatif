# Module `prediction` — Prédiction de pics de consommation

Suivi d'implémentation. À lire avant de reprendre EN-39 (entraînement).

---

## 1. Où on en est

| Ticket | Sujet | État |
|---|---|---|
| **EN-37** | Feature engineering séries temporelles | **Fait** |
| **EN-263** | Constitution et split du jeu d'entraînement | **Fait** |
| EN-39 | Entraînement + évaluation du modèle | À faire — consomme `split_train_test()` |

## 2. Le pipeline ML, vue d'ensemble

Une régression linéaire apprend `consommation ≈ a·f1 + b·f2 + c·f3 + d` à partir
d'exemples passés. Il lui faut, pour chaque exemple :

- **X** — les *features* : `lag_1h`, `lag_24h`, `rolling_mean_24h`
- **y** — la *cible* : la consommation **1 h plus tard** (T+1h), pas à l'instant T

L'historique brut en base est une simple série chronologique ; une régression
n'a aucune mémoire d'une ligne à l'autre. EN-37 transforme cette série en un
tableau où **chaque ligne se suffit à elle-même** ; EN-263 y ajoute la cible et
découpe train / test.

```
EN-37                     EN-263                          EN-39
──────────────────        ─────────────────────────       ──────────────────────
get_measurements()   →    build_dataset()            →    model.fit(X_train,
add_time_features()          + target = conso T+1h            y_train)
  + lag_1h, lag_24h,           (shift(-60) par site)       évaluation sur
    rolling_mean_24h       split_train_test()               (X_test, y_test)
                            dropna(features + target)      sauvegarde du modèle
                            cutoff chronologique 80/20
                            → X_train, X_test,
                              y_train, y_test
```

Plus tard : `model.predict()` sur des features fraîches ; si la conso prévue
dépasse le seuil du site → alerte « pic ».

EN-37 et EN-263 **ne font aucun entraînement** : ils préparent la matière
première.

## 3. Fichiers livrés

| Fichier | Rôle |
|---|---|
| `features/time_features.py` | EN-37 — `add_time_features(df)`, fonction **pure**, zéro I/O |
| `repository/measurement_repository.py` | `get_measurements(site_id=None)` — extraction SQL, renvoie un `DataFrame` |
| `dataset/dataset.py` | EN-263 — `build_dataset()` (features + cible T+1h) et `split_train_test()` (cutoff chronologique) |
| `main.py` | Scaffold du worker — boucle d'inférence à brancher en EN-39 |
| `tests/test_time_features.py` | EN-37 : les 4 critères d'acceptation + la neutralisation |
| `tests/test_measurement_repository.py` | La requête SQL (mockée) |
| `tests/test_dataset.py` | EN-263 : les 4 critères d'acceptation + cible future + garde-fous |
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

### 4.7 EN-263 — cible dans le futur, split chronologique

- **Cible = conso à T+1h**, pas à T. Prédire la conso *à l'instant présent* ne
  sert à rien (la vraie mesure arrive de toute façon en direct via l'ETL).
  `target = groupby("site_id")["consumption_kw"].shift(-HORIZON_ROWS)` — décalage
  **négatif**, par site. `HORIZON_ROWS = ROWS_PER_HOUR` (60), constante unique.
- **Horizon 1 h = choix MVP.** C'est court pour « anticiper un pic », mais c'est
  l'horizon où nos 3 features sont vraiment prédictives, ce qui permet de valider
  toute la chaîne avec un modèle simple. À rediscuter avec le métier (6 h ? 24 h ?)
  — un horizon plus long imposerait d'autres features (calendaires, météo).
- **Split par date, jamais aléatoire.** Sur une série temporelle, un split
  aléatoire entraînerait le modèle sur des dates postérieures au test — situation
  impossible en prod. Cutoff : 80 % des dates les plus anciennes → train, 20 %
  les plus récentes → test (`DEFAULT_CUTOFF_RATIO`).
- **Cutoff global** sur toute la table (pas par site). Suppose des historiques
  comparables entre sites ; isolé dans `_split_by_cutoff` pour bascule facile en
  per-site si le volume devient très inégal.
- **Pas d'embargo** au niveau du cutoff (les ~60 lignes de train juste avant le
  cutoff ont une cible qui tombe dans la fenêtre du test) — assumé pour le MVP.
- **`dropna` sur `features + target`**, pas sur `consumption_kw` à T : la conso à
  T ne sert plus que d'intermédiaire (features + cible), une ligne reste valide
  même si sa `consumption_kw` est `NaN`.
- **Garde-fous** : `NotEnoughDataError` si < 2 lignes après nettoyage, ou si le
  cutoff laisse train/test vide.

## 5. Critères d'acceptation → tests

**EN-37** (`test_time_features.py`)

| Critère | Test |
|---|---|
| Lags par `site_id`, jamais mélangés | `test_lags_are_computed_per_site_and_never_mixed` |
| Lags `null` si historique insuffisant | `test_lags_are_null_when_history_is_insufficient` |
| `shift()` avant `rolling()` | `test_rolling_mean_shifts_before_rolling_and_excludes_current_row` |
| Aucune fuite de données (feature T ⟂ conso T) | `test_no_data_leakage_from_current_row` |
| (bonus) neutralisation `null_reason` | `test_tainted_consumption_is_neutralized_but_row_is_kept` |

**EN-263** (`test_dataset.py`)

| Critère | Test |
|---|---|
| Split chronologique, jamais aléatoire | `test_split_respects_chronological_order` |
| Aucune date test antérieure à une date train | `test_no_test_date_precedes_a_train_date` |
| Aucune ligne à feature/cible manquante dans train ou test | `test_missing_feature_or_target_rows_are_excluded` |
| Ratio 80/20 documenté et vérifié | `test_default_ratio_is_roughly_80_20` |
| (bonus) cible = valeur future, par site | `test_build_dataset_target_is_consumption_one_hour_later_per_site` |
| (bonus) garde-fous données insuffisantes | `test_raises_when_dataset_too_small`, `test_raises_when_all_rows_share_one_date` |

Tous les tests tournent sur des `DataFrame` synthétiques — **aucune base réelle
nécessaire**.

## 6. Lancer les tests

```bash
# depuis la racine du repo, venv activé
python -m pytest backend/prediction/tests --cov=backend/prediction --cov-report=term-missing --cov-fail-under=80
```

État actuel : `19 passed`, couverture `~99 %` (seuil CI : 80 %).

La CI ([.github/workflows/ci-cd.yml](../../.github/workflows/ci-cd.yml)) lance
chaque service isolément avec un `PYTHONPATH` dédié. Lancer `pytest backend` en
entier échoue à la collecte (collision SQLAlchemy `etl` + `core` sur
`ener.measurement`) — c'est **pré-existant** et sans rapport avec ce module.

## 7. Pour EN-39 (entraînement)

Tout est prêt en entrée. L'enchaînement :

```python
from prediction.dataset.dataset import build_dataset, split_train_test

X_train, X_test, y_train, y_test = split_train_test(build_dataset())

model = LinearRegression()
model.fit(X_train, y_train)
# évaluation sur (X_test, y_test), puis sauvegarde du modèle + model_version
```

- `split_train_test` renvoie exactement le 4-uplet attendu par scikit-learn ;
  `X_*` ne contient que `FEATURE_COLUMNS` (ni `site_id` ni `measurement_date`).
- Gérer `NotEnoughDataError` (peu de données au démarrage → normal, cf. 4.5).
- **Comparer le modèle à une baseline bête** (« conso dans 1 h = conso d'il y a
  1 h », ou « = hier même heure »). S'il ne bat pas ça, l'approche est à revoir.
- `data_quality` / `null_reason` restent dans `build_dataset()` (pas dans `X`)
  si EN-39 veut filtrer/analyser les lignes dégradées.
- Le worker `main.py` remplacera son scaffold par : `build_dataset` →
  `split_train_test` (ou chargement d'un modèle déjà entraîné) → `predict` →
  écriture dans `ener.prediction` (`site_id`, `predicted_for`,
  `predicted_consumption_kw`, `model_version`) → boucle.

## 8. Note : refactor `core` → `shared`

Un merge de `develop` pendant l'implémentation a déplacé `core/database.py` →
`shared/database.py` (et `core/base.py` → `shared/base.py`). L'import du
repository a été mis à jour en conséquence (`from shared.database import
engine`).
