# Machine Learning / MLOps — EnerVision

Documentation du cycle MLOps du service `backend/prediction/` : dataset,
entraînement, baseline, drift, promotion champion/challenger, service
d'inférence, API, observabilité. Modèle : `LinearRegression`
(`sklearn.linear_model.LinearRegression`), désormais **multi-output**
(§Forecast multi-horizon ci-dessous), sur huit features (`lag_1h`, `lag_24h`,
`lag_168h`, `rolling_mean_24h`, `rolling_mean_168h`, `hour_of_day`,
`day_of_week`, `is_weekend`).

---

## Forecast multi-horizon (T+1h → T+7j)

### Pourquoi le besoin a évolué

Le service ne répondait qu'à « quelle sera la consommation dans 1h ? ».
Afficher une courbe (frontend/Grafana/autre) exige une **prévision continue**
sur plusieurs jours, pas une valeur isolée. Le modèle prédit désormais, en un
seul appel, une valeur par heure de **T+1h à T+168h** (7 jours), granularité
1h, horizon minimum 1h, horizon maximum 168h.

### Stratégie ML retenue : régression directe multi-horizon, matérialisée en multi-output

Trois familles de stratégies ont été comparées avant tout code :

| Stratégie | Propagation d'erreur | Coût entraînement | Complexité / artefacts | Retenue |
|---|---|---|---|---|
| **Récursive** (modèle T+1h réinjecté 168 fois) | Cumulative sur 168 pas — explicitement écartée par le besoin | Faible (1 modèle) | Faible | ❌ |
| **168 modèles indépendants** (un par horizon) | Aucune (direct) | ~168× (négligeable pour `LinearRegression`, mais 168 artefacts) | Élevée : 168 `Registered Model`/versions à gérer, casse le principe « un seul `consumption-predictor` » | ❌ |
| **Multi-output** (`LinearRegression.fit(X, Y)`, `Y` = 168 colonnes cibles) | Aucune (direct) | ~1× (une seule résolution des moindres carrés, plusieurs colonnes) | Faible : **un seul objet Python, un seul artefact MLflow, un seul Registered Model** | ✅ |

`LinearRegression` de scikit-learn accepte nativement une cible 2D
(`n_échantillons × n_horizons`) : chaque colonne de sortie est résolue de
façon indépendante par les moindres carrés (mathématiquement identique à 168
régressions séparées sur le même `X`), mais reste **un seul estimateur
scikit-learn**, chargé/loggé/servi comme un objet unique. Ce choix :

- **Direct, jamais récursif** : chaque horizon est une sortie directe du
  modèle à partir des features de l'instant T (l'ancre) — aucune prédiction
  n'est réinjectée comme feature pour l'horizon suivant, donc aucune
  propagation d'erreur (`inference/prediction_service.py::_predict_all_horizons`
  fait **un seul** appel `model.predict(X)` par requête, quel que soit
  `hours`, vérifié par
  `tests/test_prediction_service.py::test_forecast_calls_feature_builder_exactly_once_not_recursively`).
- **Compatible avec `LinearRegression`** : aucun changement d'algorithme
  demandé par le besoin.
- **Un seul Registered Model** (`consumption-predictor`, conservé) : pas de
  prolifération de modèles/aliases à gérer dans le Registry.
- **Explicable devant un jury** : « même modèle linéaire, 168 sorties
  calibrées simultanément sur le même vecteur de features », pas de boîte
  noire supplémentaire.
- **Entraînement toujours quasi instantané** pour `LinearRegression` (une
  résolution de moindres carrés, même avec 168 colonnes de sortie).

### Ce que prédit désormais le modèle

168 cibles simultanées : `target_h1` (= `consumption_kw` à T+1h, alias
`TARGET_COLUMN` historique, conservé) jusqu'à `target_h168` (= `consumption_kw`
à T+168h), chacune `groupby("site_id")["consumption_kw"].shift(-h·60)` — même
mécanique que la cible T+1h existante, généralisée (`dataset/dataset.py::build_dataset`).

### Features ajoutées, prévention des fuites temporelles

Les 3 features historiques (`lag_1h`, `lag_24h`, `rolling_mean_24h`) ne
portent aucun signal de saisonnalité hebdomadaire — insuffisant pour un
horizon à 7 jours. Ajoutées (`features/time_features.py::add_time_features`),
avec la même discipline anti-fuite que l'existant (`shift`/`rolling` par
site, jamais de valeur future) :

- **`lag_168h`**, **`rolling_mean_168h`** : mêmes mécaniques que `lag_24h`/
  `rolling_mean_24h`, décalées à 7 jours (`ROWS_PER_WEEK = 7 × ROWS_PER_DAY`).
- **`hour_of_day`, `day_of_week`, `is_weekend`** : fonctions pures et
  déterministes de `measurement_date` **de la ligne T elle-même** (jamais de
  l'instant cible T+h) — aucun historique requis, aucune fuite possible par
  construction (`tests/test_time_features.py::test_calendar_features_never_depend_on_consumption_value`).

Un seul vecteur de features `X` (calculé à l'instant T, l'ancre) sert à
prédire **les 168 horizons** — c'est ce qui permet à un seul appel
`model.predict(X)` de produire toute la courbe. Conséquence assumée : une
ligne n'est exploitable à l'entraînement que si son **passé** (7 jours, pour
`lag_168h`) et son **futur** (7 jours, pour `target_h168`) sont tous deux
connus (`dataset/dataset.py::clean_multi_horizon_dataset`) — réduit la fenêtre
utilisable aux lignes dont les 7 jours suivants sont déjà observés, attendu
pour un entraînement multi-horizon honnête, pas un bug.

Le même code (`add_time_features`, `FEATURE_COLUMNS`) est utilisé à
l'entraînement (`training/pipeline.py`) et à l'inférence
(`inference/feature_builder.py::build_latest_features`) : aucune divergence
possible entre les deux.

### Baseline multi-horizon

Revue pour ne jamais comparer le candidat à une règle trop faible ou
arbitraire (`training/baseline.py`). Deux régimes, toujours calculables
depuis le passé strict (jamais de fuite) :

- **h ≤ 24h : persistance** — `baseline(T+h) = consumption_kw(T)`. C'est la
  règle naïve la plus dure à battre à court terme (forte autocorrélation),
  donc la référence la plus honnête.
- **h > 24h : « même heure, la semaine précédente »** — `baseline(T+h) =
  consumption_kw(T+h-168h)`. Comme `h ≤ 168h`, `T+h-168h ≤ T` : toujours
  connue en T, quel que soit `h`. Un régime « même heure hier » (24h) a été
  jugé redondant avec la persistance sur 1..24h et inutile au-delà — deux
  régimes suffisent à couvrir 1..168h simplement.

### MAE par horizon, jamais une seule MAE globale

Le détail complet (`mae_h1`..`mae_h168`, `baseline_mae_h1`..`baseline_mae_h168`)
est calculé (`training/pipeline.py::_mae_by_horizon`) et loggé en **artefact
MLflow JSON** (`mae_by_horizon.json`) — jamais en 168 métriques MLflow
séparées (illisible). Trois horizons clés (`mae_h1`, `mae_h24`, `mae_h168`,
`baseline_mae_h1`, `baseline_mae_h24`, `baseline_mae_h168`, `mae_mean`) sont
en plus loggés comme **métriques MLflow scalaires**, lisibles directement
dans l'UI et exposées en Prometheus (`ml_mae_h24`, `ml_mae_h168`, etc. —
voir §Prometheus).

### Règle de promotion multi-horizon

Un candidat excellent à T+1h mais catastrophique à T+168h ne doit jamais
devenir champion. `training/pipeline.py::_decide_promotion` exige que le
candidat batte la baseline **puis** (s'il existe) le champion
**simultanément** aux trois horizons clés (h1, h24, h168) — pas en moyenne :
si un seul de ces horizons ne satisfait pas le seuil configuré
(`MIN_IMPROVEMENT_VS_BASELINE`/`MIN_IMPROVEMENT_VS_CHAMPION`, inchangés), le
candidat est rejeté, avec le détail de l'horizon fautif dans le message de
raison. `mae_mean` reste une information complémentaire (loggée), jamais un
critère de décision. Le principe **baseline → challenger → champion** et les
alias MLflow existants sont conservés à l'identique.

### API

`GET /api/v1/sites/{site_id}/prediction` (T+1h) est **conservé sans
changement de contrat** — en interne, c'est désormais le premier point d'un
`forecast(hours=1)` sur le même modèle multi-output.

Ajouté : `GET /api/v1/sites/{site_id}/forecast?hours=24` (défaut 24,
1 ≤ hours ≤ 168, validé par FastAPI `Query(ge=1, le=168)` → `422`
automatique hors plage). Réponse : `ForecastResponse` (`api/schemas.py`),
avec une distinction explicite entre trois instants (§5 du besoin) :

- **`generated_at`** : horloge système, instant réel de l'appel API.
- **`base_timestamp`** : dernière mesure réellement utilisée pour construire
  les features (peut être **postérieure** à `generated_at` avec un dataset
  simulé/historique — jamais filtré par `measurement_date <= NOW()`).
- **`target_timestamp`** (par point) : `base_timestamp + horizon_hours`
  heures — **jamais** calculé depuis `generated_at`.

Le contrôleur (`api/controller/prediction.py`) reste mince : aucune logique
ML, seulement validation d'entrée, appel au service, mapping d'exceptions
(factorisé entre `/prediction` et `/forecast` via `_map_inference_errors`) et
sérialisation. Toute la logique de forecast vit dans
`inference/prediction_service.py::PredictionService.forecast`.

### PostgreSQL

`ener.prediction` est réutilisée telle quelle : un forecast de N heures =
N lignes (`predicted_for` différent par ligne), inséré en un seul lot
(`repository/prediction_repository.py::record_predictions`, une transaction
pour jusqu'à 168 lignes plutôt que 168 allers-retours).

**Une seule migration additive** : `db/migrations/V01_09__add_prediction_horizon_hours.sql`
ajoute `horizon_hours INTEGER` (nullable, non-bloquant, aucune ligne
existante modifiée, aucune migration existante touchée). Nécessaire — pas
un confort — parce qu'un appel `/forecast?hours=168` insère jusqu'à 168
lignes par appel : sans un moyen fiable de distinguer l'horizon d'une ligne,
la comparaison "performance réelle" (`get_matched_predictions`) mélangerait
des prédictions de tous les horizons, faussant la MAE réelle comparée à la
MAE de référence (calculée à T+1h). Dériver l'horizon depuis
`predicted_for - created_at` a été explicitement écarté : avec un dataset
simulé/historique dont `measurement_date` peut être postérieur à l'horloge
système (§5 du besoin), cette différence ne reflète pas l'horizon réel.

### Performance réelle par horizon

`get_matched_predictions(model_version, horizon_hours=1)` filtre désormais
sur un horizon précis (défaut 1h, l'horizon de référence historique du
champion) — la comparaison prédiction/réel utilisée par
`retrain/signals.compute_real_performance` reste donc, comme avant, ancrée
sur l'horizon T+1h uniquement (aucun changement de comportement du
réentraînement conditionnel). La fonction accepte n'importe quel horizon
(1, 24, 168, ...) pour une inspection manuelle de la performance réelle à
d'autres horizons ; câbler cela dans `should_retrain` a été jugé disproportionné
pour l'instant (§Limites) — pas de nouvel endpoint HTTP dédié, non demandé
par le besoin.

### Drift

`DRIFT_FEATURE_COLUMNS` (`dataset/dataset.py`) couvre les 5 features
« consommation passée » (`lag_1h`, `lag_24h`, `lag_168h`, `rolling_mean_24h`,
`rolling_mean_168h`). Les 3 features calendaires (`hour_of_day`,
`day_of_week`, `is_weekend`) en sont **explicitement exclues** : leur
distribution est mécaniquement stable (le calendrier boucle toujours de la
même façon) — un PSI dessus ne mesurerait qu'un artefact d'échantillonnage de
la fenêtre d'entraînement, jamais une vraie dérive du signal de consommation,
et risquerait de déclencher des réentraînements sans justification métier.

### Prometheus

Ajoutés, sans label à forte cardinalité (jamais `site_id`, `timestamp`,
`run_id`, `prediction_id`) : `forecast_requests_total{result}`,
`forecast_errors_total{reason}`, `forecast_latency_seconds`,
`forecast_points_generated_total`, `ml_mae_h24`, `ml_mae_h168`,
`ml_baseline_mae_h24`, `ml_baseline_mae_h168` (rafraîchies depuis le run
MLflow le plus récent, même mécanisme que les gauges `ml_*` existantes).

### Limites (honnêteté sur la qualité à long horizon)

Produire une valeur à T+168h ne signifie **pas** que cette valeur est
fiable — c'est précisément pour éviter cette confusion que la MAE est
calculée et loggée **par horizon** (jamais une seule MAE globale qui la
masquerait) : `baseline_mae_h1 < baseline_mae_h24 < baseline_mae_h168`
observé systématiquement sur les jeux de test (la baseline elle-même se
dégrade avec l'horizon), et `mae_h168` doit être lu en regard de
`baseline_mae_h168`, jamais en absolu. Une `LinearRegression` peut être
excellente à T+1h et significativement moins bonne à T+7j — la règle de
promotion (ci-dessus) est conçue pour ne jamais masquer cette dégradation,
mais elle ne la fait pas disparaître : la qualité réelle à 7 jours dépend du
volume et de la nature des données de production, à valider en conditions
réelles (voir §Limitations en fin de document).

---

## Architecture

```
backend/prediction/
├── main.py                       CLI : train | train-if-needed | serve
├── config.py                     Variables d'environnement MLOps centralisées
│
├── repository/
│   ├── measurement_repository.py   (existant) lecture ener.measurement
│   └── prediction_repository.py    (nouveau) écriture/lecture ener.prediction
│
├── features/
│   └── time_features.py          (existant, inchangé) lag_1h, lag_24h, rolling_mean_24h
│
├── dataset/
│   └── dataset.py                (étendu) build_dataset, split_train_test (2 voies,
│                                  conservé), split_train_val_test (nouveau, 3 voies)
│
├── training/
│   ├── training_service.py       (modifié) train_model/evaluate_model — primitives MLflow
│   ├── baseline.py               (nouveau) baseline lag_1h, MAE, amélioration relative
│   └── pipeline.py               (nouveau) orchestration complète d'un entraînement
│
├── drift/
│   └── drift_service.py          (nouveau) PSI par feature, référence/détection
│
├── registry/
│   └── model_registry.py         (nouveau) wrapper MLflow Model Registry (alias)
│
├── retrain/
│   ├── decision.py               (nouveau) should_retrain(...) — pure
│   ├── signals.py                (nouveau) nouvelles données / performance réelle
│   └── orchestrator.py           (nouveau) train_if_needed()
│
├── inference/
│   ├── feature_builder.py        (nouveau) features du dernier point d'un site
│   └── prediction_service.py     (nouveau) cache champion + prédiction + historisation
│
├── observability/
│   └── ml_metrics.py             (nouveau) métriques Prometheus (HTTP métier + ml_*)
│
└── api/
    ├── app.py                    (nouveau) application FastAPI (`serve`)
    ├── schemas.py                 (nouveau) PredictionResponse
    └── controller/
        ├── health.py              (nouveau) /health
        └── prediction.py          (nouveau) GET /api/v1/sites/{site_id}/prediction
```

**Modules créés** : `training/baseline.py`, `training/pipeline.py`,
`drift/drift_service.py`, `registry/model_registry.py`, `retrain/decision.py`,
`retrain/signals.py`, `retrain/orchestrator.py`, `inference/feature_builder.py`,
`inference/prediction_service.py`, `observability/ml_metrics.py`,
`api/app.py`, `api/schemas.py`, `api/controller/health.py`,
`api/controller/prediction.py`, `repository/prediction_repository.py`,
`config.py`.

**Modules modifiés** : `dataset/dataset.py` (ajout `split_train_val_test`,
`clean_dataset`, généralisation de `_split_by_cutoff`), `training/training_service.py`
(`train_model` ne fait plus l'auto-registration MLflow — voir §MLflow),
`main.py` (devient un vrai CLI à sous-commandes), `Dockerfile`
(sert l'API par défaut).

**Modifiés pour le correctif MLflow/artefacts** (voir §MLflow — Architecture
des artefacts pour le détail) : `training/training_service.py`
(`log_model(name=...)`, `train_model` renvoie aussi `model_uri`),
`registry/model_registry.py` (`register_challenger` prend `model_uri` au
lieu de reconstruire une URI `runs:/`, nouvelle exception
`ChampionLoadError`), `training/pipeline.py` (champion cassé n'interrompt
plus l'entraînement, tag `recovered_from_broken_champion`),
`retrain/decision.py` et `retrain/orchestrator.py` (nouvelle raison
`champion_unavailable`), `api/controller/prediction.py` (distingue
`ChampionLoadError` de `NoChampionModelError`, toujours `503`),
`docker-compose-data.yaml` (`mlflow` : `--serve-artifacts`/`--artifacts-destination`
au lieu de `--default-artifact-root`, healthcheck), `docker-compose.yaml`
(`prediction` attend `mlflow: condition: service_healthy`).

**Non modifiés** : `features/time_features.py` (aucun bug détecté — voir
§Dataset), `repository/measurement_repository.py`.

Aucune couche/abstraction superflue n'a été ajoutée : chaque nouveau module
correspond à une responsabilité listée explicitement dans le besoin
(baseline, drift, decision, registry, inference, observabilité, API).

---

## Dataset

- **Source** : `ener.measurement` (PostgreSQL), via
  `repository/measurement_repository.get_measurements(site_id=None)`
  (inchangé).
- **Features** (inchangées, calculées par `features/time_features.add_time_features`) :
  `lag_1h` (`shift(60)`), `lag_24h` (`shift(1440)`), `rolling_mean_24h`
  (`shift(1).rolling(1440, min_periods=1).mean()`) — 1 mesure/minute, donc
  décalage par nombre de lignes. Neutralisation des `consumption_kw`
  recopiées par le forward-fill de l'ETL via `null_reason` (inchangé).
- **Target** : `consumption_kw` à **T+1h**, soit
  `groupby("site_id")["consumption_kw"].shift(-HORIZON_ROWS)` avec
  `HORIZON_ROWS = ROWS_PER_HOUR = 60` (inchangé).
- **Nettoyage** : `dataset.clean_dataset(df)` (nouveau, factorisé) —
  `dropna` sur `FEATURE_COLUMNS + [TARGET_COLUMN]`, tri par
  `measurement_date`. Utilisé par le split et par le calcul de drift /
  volume de nouvelles données, pour une définition unique de "ligne
  exploitable" dans tout le module.
- **Aucun bug détecté** dans le calcul des lags/target existant : le
  `shift(1)` avant `rolling`, le calcul par site via `groupby`, et le décalage
  négatif pour la cible sont corrects et déjà couverts par
  `tests/test_time_features.py` et `tests/test_dataset.py` (conservés tels
  quels). Aucune migration liée aux données n'a donc été nécessaire ici.
- **Split temporel** : voir §Validation.

---

## Modèle

- **`sklearn.linear_model.LinearRegression`**, conservée intégralement (pas
  d'hyperparamètres à faire varier, `fit_intercept=True` comme avant).
  Conservée parce que c'est la demande explicite du besoin : l'objectif est
  d'industrialiser le cycle MLOps autour d'un modèle simple et interprétable,
  pas de chercher un meilleur algorithme.
- **Entraînement** : `training/training_service.train_model(X_train, y_train, dvc_hash=None)`
  — inchangé dans son comportement (log `fit_intercept`, `n_train_rows`,
  `dvc_hash` si fourni, log du modèle sklearn). **Un seul changement** :
  `mlflow.sklearn.log_model(...)` ne prend plus `registered_model_name`.
  Avant, *chaque* appel à `train_model` créait silencieusement une nouvelle
  version de modèle enregistrée, y compris pour des essais/tests. Désormais
  l'enregistrement dans le Model Registry est une décision explicite du
  pipeline (`registry.register_challenger`), après évaluation — cohérent
  avec "un candidat non prometteur ne doit jamais polluer le Registry sans
  raison".
- **Inférence** : `inference/prediction_service.PredictionService.predict(site_id)`
  charge le modèle champion (cache), construit les features du point le plus
  récent du site, appelle `model.predict(X)`.

---

## Baseline

- **Définition** (`training/baseline.py`) : `predict_baseline(X) = X["lag_1h"]`
  — "la conso dans 1h sera la même qu'il y a 1h", conforme à la sémantique
  actuelle du dataset (`lag_1h` = `consumption_kw` à `T-1h`).
- **MAE baseline** : `baseline_mae(X, y) = mean_absolute_error(y, predict_baseline(X))`,
  calculée sur le **même jeu de test** que le candidat.
- **Amélioration relative** :
  `relative_improvement(reference_mae, candidate_mae) = (reference_mae - candidate_mae) / reference_mae`.
  Utilisée à la fois pour `mae_improvement_vs_baseline` (référence = baseline)
  et `mae_improvement_vs_champion` (référence = champion). Positive si le
  candidat fait mieux, négative sinon. `reference_mae == 0` → `0.0` si le
  candidat est parfait aussi, sinon `-inf` (rejet garanti, pas de division
  par zéro).
- **Critère de promotion** : le candidat est rejeté si
  `mae_improvement_vs_baseline < MIN_IMPROVEMENT_VS_BASELINE`
  (défaut **0.05**, soit 5 % de MAE en moins que la baseline). Seuil choisi
  pour éviter qu'un modèle à peine meilleur qu'une règle triviale ne soit
  promu — configurable si le métier juge 5 % trop strict/laxiste.

---

## Validation

- **Split chronologique à trois voies** (`dataset.split_train_val_test`,
  défauts **70 % train / 15 % validation / 15 % test**) : implémenté via
  `_split_by_cutoffs(df, cumulative_ratios)`, une généralisation de l'ancien
  `_split_by_cutoff` à N tranches contiguës. `split_train_test` (2 voies,
  80/20) est **conservé** tel quel — toujours testé, toujours utilisé comme
  utilitaire simple — mais `training/pipeline.py` (le chemin réellement
  exécuté en production) utilise exclusivement le split à 3 voies.
- **Rôle de chaque ensemble** :
  - **train** → `model.fit(...)`.
  - **validation** → calcul de `validation_mae` (diagnostic loggé dans
    MLflow, non utilisé dans la décision de promotion — voir Limitations).
  - **test** → **seul** ensemble utilisé pour `mae`, `baseline_mae`,
    `champion_mae` et la décision de promotion. Le split est calculé une
    seule fois par run ; aucune configuration n'est choisie *en fonction* du
    résultat sur le test, donc pas de fuite indirecte.
- **Prévention des fuites temporelles** :
  - Découpage strictement chronologique (`PASSÉ → train`,
    `futur proche → validation`, `futur plus récent → test`), jamais aléatoire.
  - `rolling_mean_24h` utilise `shift(1)` avant `rolling` (déjà en place) :
    aucune feature de la ligne T n'utilise `consumption_kw[T]`.
  - Le champion est ré-évalué sur le **même** jeu de test que le challenger
    avant toute comparaison (`training/pipeline.py`), jamais sur les
    métriques historiques de son propre run d'entraînement — cf. §MLflow.
  - Pas d'embargo autour des cutoffs (hérité du comportement existant,
    assumé pour ce volume de données — cf. Limitations).

---

## Drift

- **Méthode : PSI (Population Stability Index)** par feature
  (`lag_1h`, `lag_24h`, `rolling_mean_24h`), implémentée dans
  `drift/drift_service.py`. Choisie plutôt qu'un KS-test pour :
  - **simplicité/explicabilité** : un score par feature, un seuil unique,
    facile à exposer en métrique Prometheus (`ml_drift_score{feature=...}`) ;
  - **peu de dépendances** : seulement `numpy` (déjà une dépendance
    transitive de pandas/scikit-learn) ;
  - **robustesse** aux faibles cardinalités (les bins se réduisent
    proprement au lieu d'échouer, cf. `_bin_edges`).
- **Calcul** : `compute_reference_stats(df, feature_columns, n_bins=10)`
  découpe chaque feature de référence en déciles (bornes `-inf`/`+inf` aux
  extrémités pour absorber toute valeur future hors plage), stocke les
  proportions par bin. `detect_drift(reference_stats, current_df, threshold)`
  rebine les valeurs courantes sur les **mêmes bornes**, calcule
  `PSI = Σ (cur_i - ref_i) * ln(cur_i / ref_i)` (proportions planchées à
  `1e-4` pour éviter `log(0)`), et marque une feature "en dérive" si son PSI
  `>= threshold`.
- **Référence** : les statistiques de référence sont calculées sur
  l'**ensemble train** du run qui a produit le champion, et sauvegardées
  comme artefact MLflow JSON (`drift_reference.json`) attaché **au run**
  (donc versionné avec le modèle et son `run_id`/version). Elles ne sont
  **réécrites que quand un nouveau candidat est promu champion**
  (`training/pipeline.py`, `registry.save_drift_reference`), jamais à chaque
  entraînement. Aucune donnée brute n'est dupliquée dans MLflow — seulement
  bornes de bins + proportions (quelques dizaines de flottants).
- **Seuil** : `DRIFT_THRESHOLD`, défaut **0.2** (repère usuel : `< 0.1` pas de
  dérive significative, `0.1–0.25` dérive modérée, `> 0.25` dérive majeure —
  0.2 est un compromis raisonnable pour ne déclencher un réentraînement que
  sur une dérive réellement notable).
- **Interprétation** : `DriftResult.drift_detected` est `True` si **au moins
  une** feature dépasse le seuil ; `drifted_features` liste lesquelles ;
  `feature_scores` donne le score de chacune ; `skipped_features` liste
  celles ignorées (pas de référence, ou pas de valeur courante — jamais
  d'invention de score).

---

## Réentraînement

- **`retrain/decision.should_retrain(has_champion, drift_result, n_new_rows,
  min_new_rows, real_performance=None)`** (pure, testée indépendamment de
  MLflow/Postgres) retourne `RetrainDecision(should_retrain, reasons)`.
  Raisons possibles, chacune suffisante isolément :
  - `no_existing_champion` — premier entraînement.
  - `data_drift_detected` — au moins une feature en dérive par rapport à la
    référence du champion.
  - `enough_new_data` — `n_new_rows >= MIN_NEW_ROWS` lignes exploitables
    accumulées depuis l'entraînement du champion. `MIN_NEW_ROWS` (défaut
    **1440**, soit ~1 jour de données à 1 mesure/minute) sert de cadence de
    réentraînement périodique même sans dérive détectée, en plus d'être un
    filtre "pas assez de nouveauté pour justifier un entraînement".
  - `real_performance_degraded` — MAE réelle récente du champion
    `> 1.2 ×` sa MAE enregistrée à la promotion (facteur interne au code,
    pas une variable d'environnement : c'est un détail d'implémentation de
    la règle, pas un paramètre métier à faire varier par déploiement).
  - `champion_unavailable` — un champion est enregistré (alias `champion`
    présent, `ModelVersion` à l'état `READY`) mais son artefact modèle n'a
    pas pu être chargé (`registry.ChampionLoadError`, voir §MLflow —
    Robustesse champion cassé). Détecté par `train_if_needed` via un essai
    de chargement dédié, distinct de la simple présence de l'alias.
- **`retrain/signals.py`** fournit les deux entrées "réelles" que la config
  seule ne peut pas donner :
  - `count_new_rows_since_champion` — compte les lignes de
    `clean_dataset(df)` postérieures à `dataset_max_date`, un **paramètre**
    loggé sur **chaque** run d'entraînement (`training/pipeline.py`) avec la
    date la plus récente du dataset utilisé.
  - `compute_real_performance` — voir section suivante.
- **`retrain/orchestrator.train_if_needed()`** enchaîne : construire le
  dataset → chercher le champion → **essayer de le charger** (détection de
  `champion_unavailable`) → calculer le drift (test set) → calculer
  les deux signaux → `should_retrain(...)` → logger la décision → **ne rien
  faire** si `should_retrain=False`, sinon appeler
  `training.pipeline.run_training_pipeline(trigger_source="cli_train_if_needed",
  retrain_reasons=decision.reasons)`. L'essai de chargement du champion
  déserialise réellement le modèle (coût négligeable pour une
  `LinearRegression`) : c'est la seule façon fiable de détecter un artefact
  cassé, une vérification de métadonnées seule (alias présent, version
  `READY`) ne suffit pas — voir §MLflow.

### Performance réelle en production (§13 du besoin)

`ener.prediction` existait déjà en base (`site_id`, `predicted_for`,
`predicted_consumption_kw`, `model_version`, `created_at`) mais n'était
utilisée par **aucun** code avant ce travail. `inference/prediction_service.py`
y historise désormais chaque prédiction, et
`repository/prediction_repository.get_matched_predictions(model_version)`
fait la jointure :

```sql
SELECT p.site_id, p.predicted_for, p.predicted_consumption_kw,
       m.consumption_kw, m.null_reason
FROM ener.prediction p
JOIN ener.measurement m
  ON m.site_id = p.site_id AND m.measurement_date = p.predicted_for
WHERE p.model_version = :model_version
```

— c'est-à-dire : pour chaque prédiction passée dont l'horizon cible
(`predicted_for`) est désormais dans le passé, la vraie mesure est-elle
arrivée ? Les lignes dont `consumption_kw` est une recopie forward-fill
(mêmes `null_reason` que pour le feature engineering) sont exclues, pour ne
jamais comparer une prédiction à une valeur non fiable. **Aucune fuite
temporelle** : on ne compare jamais une prédiction à une mesure qui n'existe
pas encore — la jointure ne renvoie que des lignes où la mesure réelle a
effectivement été insérée par l'ETL.

**Limitation actuelle, honnêtement documentée** : cette fonctionnalité vient
d'être câblée. Tant que le service `prediction` n'a pas tourné en production
suffisamment longtemps pour accumuler des prédictions **et** que leurs
horizons cibles soient passés, `ener.prediction` ne contient pas assez de
lignes exploitables. `compute_real_performance` retourne alors
explicitement `None` (pas de simulation, pas de MAE inventée) tant que moins
de **30** prédictions non-tainted n'ont de mesure réelle associée
(`MIN_MATCHED_PREDICTIONS_FOR_REAL_PERFORMANCE`, constante de code). Dans ce
cas, `should_retrain` ignore simplement ce signal — comportement testé
explicitement (`test_retrain_decision.py::test_missing_real_performance_is_not_a_reason_to_retrain`).
Aucune migration n'a été nécessaire pour rendre cela possible : le schéma
existant suffisait.

---

## Automatisation

- **`python -m prediction.main train`** — force un entraînement (pipeline
  complet, promotion/rejet inclus), quel que soit `should_retrain`. Utile
  pour un premier entraînement manuel ou un forçage explicite.
- **`python -m prediction.main train-if-needed`** — commande destinée au
  scheduler. Ne fait **jamais** d'entraînement à chaque démarrage de
  conteneur : c'est une invocation ponctuelle, séparée du process API
  (`serve`).
- **`python -m prediction.main serve`** — lance l'API FastAPI (uvicorn),
  process long-vivant, ne déclenche jamais d'entraînement.
- **Ordonnancement réel** : aucun ordonnanceur n'existe déjà dans ce dépôt
  pour des jobs applicatifs (seul `pyway`/migration est un job Docker
  ponctuel). Conformément à la consigne ("n'introduis pas Airflow"), la
  solution proposée est un **cron/systemd timer sur le serveur de
  production**, qui exécute une invocation Docker **jetable** de l'image
  `prediction` (jamais un `docker exec` dans le conteneur API vivant, pour
  ne jamais interférer avec les requêtes de prédiction en cours) :

  ```bash
  # /opt/enervisionG3/train_if_needed.sh
  #!/usr/bin/env bash
  set -euo pipefail
  docker run --rm \
    --network g3_default \
    --env-file /opt/enervisionG3/.env \
    ghcr.io/enervisiong3/prediction:latest \
    python -m prediction.main train-if-needed
  ```

  ```ini
  # /etc/systemd/system/enervision-train-if-needed.service
  [Unit]
  Description=EnerVision - train-if-needed

  [Service]
  Type=oneshot
  ExecStart=/opt/enervisionG3/train_if_needed.sh
  ```

  ```ini
  # /etc/systemd/system/enervision-train-if-needed.timer
  [Unit]
  Description=Vérifie périodiquement si un réentraînement est nécessaire

  [Timer]
  OnCalendar=hourly
  Persistent=true

  [Install]
  WantedBy=timers.target
  ```

  - **Qui déclenche** : le timer systemd du serveur de production.
  - **Fréquence** : proposée **horaire** (`OnCalendar=hourly`) — cohérente
    avec `MIN_NEW_ROWS` par défaut (~1 jour de données), le check étant peu
    coûteux (une requête SQL + quelques appels MLflow) même s'il ne
    déclenche pas d'entraînement à chaque fois. À ajuster selon le volume
    réel de données et la fenêtre de dérive tolérée.
  - **Commande exécutée** : `python -m prediction.main train-if-needed`
    dans un conteneur jetable de l'image `prediction`.
  - **Logs** : `journalctl -u enervision-train-if-needed.service` (stdout du
    `docker run`, qui contient les logs structurés Python — voir §Observabilité).
  - **Activer** : `systemctl enable --now enervision-train-if-needed.timer`.
  - **Désactiver** : `systemctl disable --now enervision-train-if-needed.timer`.
  - **Vérifier** : `systemctl list-timers | grep enervision`,
    `systemctl status enervision-train-if-needed.timer`.

  **NON VÉRIFIÉ DANS CET ENVIRONNEMENT** : ces fichiers ne sont pas déployés
  ni testés ici — je n'ai pas accès au serveur de production ni à sa
  configuration cron/systemd réelle. La procédure ci-dessus prépare
  uniquement ce qui est nécessaire côté application (les sous-commandes CLI
  existent et sont testées) ; l'installation effective des unités systemd
  reste à faire par l'équipe ayant accès au serveur, en suivant les
  commandes ci-dessus.

---

## MLflow

**Version installée : MLflow 3.16.0** (`mlflow/Dockerfile: FROM ghcr.io/mlflow/mlflow:v3.16.0`,
`backend/prediction/requirements.txt: mlflow`, résolu à `3.16.0` — confirmé
par `python -c "import mlflow; print(mlflow.__version__)"` dans
l'environnement de test). Toutes les décisions ci-dessous sont vérifiées
contre cette version précise (le comportement du Model Registry, des
*LoggedModels* et du mode `--serve-artifacts` a changé plusieurs fois entre
MLflow 2.x et 3.x).

- **Experiment** : `consumption-prediction` (`MLFLOW_EXPERIMENT_NAME`).
- **Registered Model** : `consumption-predictor` (`MLFLOW_MODEL_NAME`).
- **Un run par entraînement** (`training/pipeline.run_training_pipeline`),
  quel que soit `trigger_source` (`cli_train` ou `cli_train_if_needed`) :
  - **Params** : `fit_intercept`, `n_train_rows` (loggés par `train_model`),
    `dvc_hash` si fourni, `n_validation_rows`, `n_test_rows`,
    `dataset_max_date` (date la plus récente du dataset utilisé — sert de
    référence à `count_new_rows_since_champion`).
  - **Metrics** : `mae` (candidat, sur le test set), `validation_mae`,
    `baseline_mae`, `mae_improvement_vs_baseline`, et — seulement si un
    champion existait déjà — `champion_mae` (champion **ré-évalué sur le
    même test set**, jamais sa métrique historique) et
    `mae_improvement_vs_champion`. Si un drift a pu être calculé (champion
    avec référence stockée) : `drift_psi_<feature>` par feature et
    `drift_detected` (0/1).
  - **Tags** : `trigger_source` (`cli_train`/`cli_train_if_needed`),
    `retrain_reasons` (raisons jointes par `,`, si déclenché par
    `train-if-needed`), et, après promotion/rejet :
    `candidate` (posé à l'enregistrement), `promoted`, `rejected`, `reason`
    (texte explicite : *"candidate mae=... does not beat baseline_mae=...
    by the required 5.0% (actual=...)"*, etc.).
  - **Model Registry** : le run est enregistré comme nouvelle version
    (`register_challenger`, à partir de l'URI réellement renvoyée par
    `train_model` — voir §Architecture des artefacts ci-dessous) — jamais
    automatiquement via `registered_model_name` sur `log_model` (voir
    §Modèle) — puis **explicitement** promue (alias `champion`, ancien alias
    `challenger` retiré) ou rejetée (alias `challenger` retiré, tags
    `rejected=true`). **Aucune version n'est jamais supprimée** :
    promotion/rejet ne touchent que des alias et des tags.
- **Champion/Challenger** : implémenté avec les **alias** du Model Registry
  (`client.set_registered_model_alias`, `get_model_version_by_alias`,
  `delete_registered_model_alias` — API moderne, pas les *stages* dépréciés,
  qui sont dépréciés depuis MLflow 2.9 et toujours dépréciés en 3.16).
  `registry/model_registry.py` centralise ces appels.
- **Promotion/rejet** — logique dans `training/pipeline._decide_promotion` :
  1. Si `mae_improvement_vs_baseline < MIN_IMPROVEMENT_VS_BASELINE` → **rejet**,
     quel que soit le champion.
  2. Sinon, si aucun champion n'existe → **promotion** (premier champion).
  3. Sinon, si le champion existant est enregistré mais que son artefact
     n'a pas pu être chargé (`champion_unavailable`, voir ci-dessous) →
     **promotion** explicitement taguée `recovered_from_broken_champion=true`
     (le candidat bat déjà la baseline à cette étape ; il n'y a rien de
     valide à comparer côté champion).
  4. Sinon, si `mae_improvement_vs_champion >= MIN_IMPROVEMENT_VS_CHAMPION` →
     **promotion** (le champion actuel est remplacé).
  5. Sinon → **rejet**, champion inchangé.
- **Historique** : `tests/test_training_pipeline.py::test_history_of_all_versions_is_preserved`
  vérifie explicitement qu'après deux promotions successives, la première
  version reste consultable via `client.get_model_version(...)`.

### Architecture des artefacts : pourquoi un simple `MLFLOW_TRACKING_URI` ne suffit pas

MLflow sépare deux choses that il est facile de confondre :

- les **métadonnées** (runs, paramètres, métriques, tags, versions de
  modèle, alias) — toujours servies via l'API REST du tracking server,
  peu importe la configuration ;
- les **artefacts** (le `.skops`/`.pkl` du modèle, `MLmodel`,
  `drift_reference.json`, …) — leur mode de service dépend **entièrement**
  de la configuration du serveur.

Un serveur MLflow peut soit (a) dire au client "voici l'URI de stockage,
débrouille-toi" (le client télécharge/upload directement, avec son propre
accès filesystem/S3/etc.), soit (b) **proxier** lui-même les artefacts via
son API REST (`--serve-artifacts`), auquel cas le client n'a jamais besoin
d'accéder au stockage sous-jacent — il ne parle qu'au tracking server en
HTTP. C'est le mode (b) qu'il faut pour une architecture multi-conteneurs où
seul le conteneur `mlflow` a accès au volume `/mlflow-artifacts`.

Le service `mlflow` (`docker-compose-data.yaml`) est configuré ainsi :

```
mlflow server
  --backend-store-uri postgresql://...
  --artifacts-destination /mlflow-artifacts
  --serve-artifacts
  --host 0.0.0.0
  --port 5000
```

`--serve-artifacts` est en réalité **activé par défaut** dans MLflow 3.16
(`mlflow server --help` : *"Default: True"*) — mais un `--default-artifact-root`
pointant vers un **chemin filesystem brut** (comme l'ancienne configuration
`--default-artifact-root /mlflow-artifacts`) **écrase ce comportement** pour
toute nouvelle expérience : celle-ci reçoit un `artifact_location` de la
forme `/mlflow-artifacts/<experiment_id>` (un chemin, pas un schéma proxifié),
et le client résout alors ses artefacts via un `LocalArtifactRepository`
**directement sur son propre filesystem** — exactement le bug rapporté. La
configuration correcte n'utilise **pas** `--default-artifact-root` ; elle
utilise `--artifacts-destination` (qui ne fixe *que* la résolution
côté serveur pour le schéma proxy `mlflow-artifacts:/`, sans jamais être
exposée telle quelle au client) combinée à `--serve-artifacts`. Avec cette
configuration, une **nouvelle** expérience reçoit un `artifact_location` de
la forme `mlflow-artifacts:/<experiment_id>` : tout accès passe alors par
`http://mlflow:5000/api/2.0/mlflow-artifacts/artifacts/...`, jamais par un
chemin local.

**Point critique, vérifié empiriquement avec cette version** : `mlflow
server --help` le dit explicitement — *"Note that this flag [`--default-artifact-root`]
does not impact already-created experiments with any previous configuration
of an MLflow server instance."* Une expérience **déjà créée** sous l'ancienne
configuration garde pour toujours son `artifact_location` en chemin brut,
même après correction de la commande serveur — **il n'existe aucune API
MLflow publique pour changer `artifact_location` a posteriori**
(`MlflowClient` n'expose que `create_experiment`, `rename_experiment`,
`set_experiment_tag`, `delete_experiment`/`restore_experiment` — vérifié par
introspection de la classe). Concrètement : si l'expérience
`consumption-prediction` de votre déploiement a été créée avant ce correctif,
**tous les runs qu'elle contient, passés et futurs, resteront non
proxifiés**, quoi que dise la commande serveur actuelle.

**Diagnostic** :

```python
import mlflow
mlflow.set_tracking_uri("http://mlflow:5000")
exp = mlflow.get_experiment_by_name("consumption-prediction")
print(exp.artifact_location)
# "mlflow-artifacts:/<id>"   -> sain, artefacts proxifiés
# "/mlflow-artifacts/<id>"   -> cassé, chemin brut hérité de l'ancienne config
```

**Remédiation, sans rien détruire** : la seule option supportée est de
repartir sur une **nouvelle** expérience. `MLFLOW_EXPERIMENT_NAME` est déjà
configurable (`config.py`) — en DEV, positionner par exemple
`MLFLOW_EXPERIMENT_NAME=consumption-prediction-v2` dans `.env`/`.env.local`
fait repartir sur une expérience saine sans toucher à l'historique de
l'ancienne (elle reste consultable dans l'UI MLflow, simplement plus
utilisée pour les nouveaux runs). Le nom par défaut dans le code
(`consumption-prediction`) n'a **pas** été changé : le faire aurait pu
casser silencieusement un déploiement dont l'expérience était en réalité
saine, ce que je ne peux pas vérifier depuis cet environnement.

### Model Registry et MLflow 3 : `LoggedModel`, `artifact_path` vs `name`

Avant ce correctif, `training_service.train_model` faisait :

```python
mlflow.sklearn.log_model(model, artifact_path="model")
```

et `model_registry.register_challenger` reconstruisait ensuite l'URI à
enregistrer à la main : `mlflow.register_model(f"runs:/{run_id}/model", ...)`.
`artifact_path=` est **déprécié en MLflow 3** ("`artifact_path` is
deprecated. Please use `name` instead.") au profit d'un nouveau concept, le
**`LoggedModel`** : `log_model()` ne se contente plus de déposer un fichier
dans les artefacts du run, il crée une entité de premier niveau (identifiant
`m-<hash>`) avec son **propre** emplacement de stockage, séparé de celui du
run. Conséquence directement vérifiée dans cet environnement : après
`mlflow.sklearn.log_model(model, artifact_path="model")`,
`MlflowClient().list_artifacts(run_id)` renvoie **`[]`** — le run n'a
littéralement aucun artefact à son nom, tout est sous le `LoggedModel`. C'est
très exactement le symptôme rapporté ("`list_artifacts(run_id)` retourne
`[]`" alors qu'une `ModelVersion` existe) : `mlflow.register_model(f"runs:/{run_id}/model",
...)` ne trouve rien à cette URI et retombe silencieusement sur le
`LoggedModel` sous-jacent (log MLflow observé : *"Run with id ... has no
artifacts at artifact path 'model', registering model based on
models:/m-... instead"*) — un filet de sécurité qui fonctionne, mais qui
masque le vrai problème et dépend d'un comportement non garanti.

**Correctif appliqué**, suivant l'API MLflow 3 recommandée :

```python
model_info = mlflow.sklearn.log_model(model, name="model")
...
return model, run.info.run_id, model_info.model_uri
```

`model_info.model_uri` est l'URI **canonique** renvoyée par `log_model()`
elle-même (`models:/m-<hash>`, pas `runs:/<run_id>/model`) —
`training_service.train_model` la renvoie désormais explicitement (nouveau
3ᵉ élément du tuple retourné), et
`model_registry.register_challenger(client, model_name, model_uri)` prend
maintenant cette URI en paramètre au lieu de reconstruire une URI `runs:/`
qui ne pointait vers rien de concret. C'est la même API pour la référence de
drift : `mlflow.log_dict(reference_stats, "drift_reference.json")` cible
bien les artefacts du **run** (pas du `LoggedModel`), donc reste inchangée —
vérifié qu'elle continue à fonctionner correctement avec `--serve-artifacts`
(voir tests `test_drift_reference_roundtrip` et
`test_drift_reference_survives_model_artifact_being_unreachable`).

### Robustesse : champion enregistré mais artefact inaccessible

`registry.load_champion_model` enveloppe désormais
`mlflow.sklearn.load_model(f"models:/{model_name}@champion")` : toute
`MlflowException` levée pendant le chargement est reconvertie en
`registry.ChampionLoadError(model_name, cause)`, une exception métier
explicite distincte de "pas de champion du tout" (qui reste signalé par
`get_champion_version(...) is None`, sans exception).

Cette distinction est propagée à travers toute la chaîne :

- **`training/pipeline.run_training_pipeline`** : si le champion existe mais
  `ChampionLoadError` est levée en tentant de le charger pour comparaison,
  l'erreur est **loggée** (`event=champion_unavailable`, avec
  `model_version`/`run_id`, `exc_info` complet — l'erreur MLflow originale
  n'est jamais masquée) et `champion_unavailable=True` est propagé à
  `_decide_promotion` (voir règle de promotion ci-dessus) et au
  `TrainingPipelineResult` retourné (nouveau champ). Le pipeline **ne
  plante pas** et **ne promeut jamais silencieusement** : la même règle
  "battre la baseline" que pour un premier champion s'applique, la raison
  de promotion mentionne explicitement la récupération, et la version
  promue reçoit un tag `recovered_from_broken_champion=true` — auditable
  dans MLflow.
- **`retrain/orchestrator.train_if_needed`** : essaie de charger le champion
  dès la phase de décision (pas seulement pendant l'entraînement) ; si
  indisponible, `champion_unavailable` devient une raison de réentraînement
  à part entière (voir §Réentraînement) — un champion cassé qui bloque déjà
  le service de prédiction est une raison largement suffisante de
  déclencher automatiquement un nouvel entraînement au prochain passage du
  scheduler, sans attendre une dérive ou un volume de données.
- **`inference/prediction_service.ChampionModelCache`** : laisse
  `ChampionLoadError` se propager telle quelle (elle n'est pas rattrapée
  localement) ; `api/controller/prediction.py` la distingue de
  `NoChampionModelError` dans ses logs et sa métrique
  (`prediction_errors_total{reason="champion_artifact_unavailable"}` contre
  `reason="no_champion_model"`), mais retourne le même code `503` dans les
  deux cas — du point de vue de l'appelant HTTP, "pas de champion" et
  "champion cassé" sont la même classe de problème : le service ne peut
  temporairement pas prédire.

---

## Prediction

- **Chargement du champion** : `inference/prediction_service.ChampionModelCache`
  résout explicitement `models:/consumption-predictor@champion` — jamais
  "la dernière version". À chaque prédiction, l'alias courant est relu
  (appel MLflow léger, métadonnées seulement) ; le modèle n'est
  **rechargé/retéléchargé que si la version a changé** depuis le dernier
  appel. Une nouvelle promotion est donc prise en compte **sans redémarrage**
  du service, au prix d'un simple appel de métadonnées par requête.
- **Features** : `inference/feature_builder.build_latest_features(site_id)`
  appelle `get_measurements(site_id)` puis **exactement** `add_time_features`
  (le même code que l'entraînement — aucune divergence possible entre
  features d'entraînement et d'inférence), prend la dernière ligne où les
  trois features sont renseignées. Lève `InsufficientHistoryError` si le
  site n'a pas d'historique exploitable (jamais de valeur inventée).
- **`PredictionService.predict(site_id, persist=True)`** : résout le modèle,
  construit les features, prédit, calcule `target_timestamp = measurement_date
  + 60 min` (cohérent avec `HORIZON_ROWS`), historise (best-effort — une
  panne Postgres est loggée mais ne fait pas échouer la prédiction), logge
  l'événement, retourne un `PredictionResult`.
- **API** — `GET /api/v1/sites/{site_id}/prediction` (voir plus bas) :
  ```json
  {
    "site_id": "SITE001",
    "prediction_timestamp": "2026-01-01T12:00:00+00:00",
    "target_timestamp": "2026-01-01T13:00:00+00:00",
    "predicted_consumption_kw": 12.34,
    "model_version": "3"
  }
  ```
  `404` si historique insuffisant, `503` si aucun champion disponible **ou**
  si un champion est enregistré mais son artefact est inaccessible
  (`ChampionLoadError`, voir §MLflow — Robustesse champion cassé), `500` sur
  toute autre erreur (loggée).

---

## PostgreSQL

- **Données utilisées** : `ener.measurement` (lecture, inchangé) et
  `ener.site` (implicitement, via `site_id`).
- **Historisation des prédictions** : réutilise la table **existante**
  `ener.prediction` (créée en `V01_01__initial_schema.sql`, contraintes
  ajoutées en `V01_03__add_constraints_not_null_defaults.sql`) — colonnes
  `site_id`, `predicted_for`, `predicted_consumption_kw`, `model_version`,
  `created_at` (défaut `now()`). Cette table n'était utilisée par **aucun**
  code avant ce travail ; elle correspondait déjà exactement au besoin
  d'historisation (§19 du besoin), donc **aucune nouvelle table** n'a été
  créée.
- **Nouvelles migrations** : **aucune**. Le schéma existant suffisait pour
  toutes les fonctionnalités demandées (baseline, drift — référence stockée
  dans MLflow, pas Postgres —, historisation, comparaison prédiction/réel).
- **Confirmation** : **aucune migration existante n'a été modifiée.** Toutes
  les migrations dans `db/migrations/` restent inchangées par ce travail
  (vérifiable via `git diff` sur ce répertoire — vide pour ce travail).

---

## Observabilité

### Logs

`logging` standard partout (jamais de `print()` pour les événements métier),
avec des champs structurés via `extra={...}` : `event`, `run_id`,
`model_name`, `model_version`, `model_alias`, `mae`, `baseline_mae`,
`champion_mae`, `drift_detected`, `drift_score`, `retrain_reason`,
`promoted`, `site_id`, `prediction`, selon pertinence. Événements couverts :
dataset construit, drift calculé, entraînement démarré/terminé/échoué,
candidat évalué, modèle promu/rejeté, modèle champion chargé, prédiction
exécutée/échouée, décision de réentraînement, échec de persistance Postgres.
Aucun secret (mots de passe, tokens, credentials) n'est jamais loggé — les
seules valeurs loggées sont des métriques, identifiants de run/version, et
raisons métier.

### Prometheus

Réutilise `prometheus-fastapi-instrumentator`, déjà en place sur
`backend/core` (même pattern : `Instrumentator().instrument(app)` +
endpoint `/metrics`). Aucune deuxième stack Prometheus créée.

**Métriques HTTP génériques** : fournies automatiquement par
l'Instrumentator (requêtes, durée, codes HTTP par endpoint).

**Métriques métier** (`observability/ml_metrics.py`), toutes dans le
registre `prometheus_client` par défaut (un seul `/metrics`) :

| Métrique | Type | Labels | Origine |
|---|---|---|---|
| `prediction_requests_total` | Counter | `result` (`success`/`error`) | in-process, à chaque appel `/prediction` |
| `prediction_errors_total` | Counter | `reason` (`insufficient_history`/`no_champion_model`/`champion_artifact_unavailable`/`unexpected`) | in-process |
| `prediction_latency_seconds` | Histogram | — | in-process |
| `ml_last_prediction_timestamp` | Gauge | — | in-process, mis à jour à chaque prédiction réussie |
| `ml_training_runs_total` | Gauge | — | recalculée depuis MLflow à chaque scrape |
| `ml_training_failures_total` | Gauge | — | idem |
| `ml_model_promotions_total` | Gauge | — | idem |
| `ml_model_rejections_total` | Gauge | — | idem |
| `ml_retraining_triggered_total` | Gauge | — | idem |
| `ml_last_training_mae` | Gauge | — | run le plus récent (MLflow) |
| `ml_baseline_mae` | Gauge | — | run le plus récent (MLflow) |
| `ml_champion_mae` | Gauge | — | champion actuel (MLflow) |
| `ml_drift_score` | Gauge | `feature` | run le plus récent (MLflow) |
| `ml_drift_detected` | Gauge | — | run le plus récent (MLflow) |
| `ml_last_successful_training_timestamp` | Gauge | — | run le plus récent (MLflow) |
| `ml_current_model_info` | Gauge | `model_name`, `alias`, `version` | champion actuel (MLflow) |

**Pourquoi des `Gauge` recalculées plutôt que des `Counter` incrémentés en
mémoire** : l'entraînement (`train`/`train-if-needed`, CLI ponctuel) et le
service API (`serve`, process long-vivant scrapé par Prometheus) sont deux
processus **distincts**. Un `Counter` incrémenté dans le process
d'entraînement serait perdu à sa sortie et jamais vu par Prometheus. MLflow
est la source de vérité (cf. §Responsabilités) : à chaque scrape de
`/metrics`, `refresh_ml_metrics()` recalcule ces métriques via quelques
appels légers au Registry/Tracking MLflow (comptage de runs/versions taggés,
dernier run). Ce n'est **pas** une recopie intégrale de MLflow dans
Prometheus — seulement une poignée de valeurs scalaires. Toute erreur MLflow
pendant ce rafraîchissement est capturée et loggée, sans jamais faire
échouer `/metrics`.

**Cardinalité** : aucun label à forte cardinalité — `result`, `reason` et
`feature` ont un nombre de valeurs fixe et petit (2, quelques dizaines max,
3), `model_name`/`alias`/`version` du `ml_current_model_info` reflètent un
seul champion courant à la fois. Aucun `site_id`, `run_id`, `prediction_id`
ou timestamp en label — ces informations restent dans les logs/MLflow/Postgres.

### Grafana

Grafana est déjà installé (`observability/docker-compose.yml`) — non
modifié. Ce dépôt ne contient pas de provisioning Grafana (pas de dossier
`provisioning/`/dashboards JSON), donc pas de dashboard livré ici : les
requêtes PromQL et panels recommandés ci-dessous sont à créer manuellement
(ou via provisioning, à ajouter séparément si souhaité).

`observability/prometheus/prometheus.yml` a été complété avec un job
`prediction` (`prediction:8000/metrics`), sur le même modèle que le job
`core` existant.

**Panels recommandés** :

| Panel | Requête PromQL |
|---|---|
| Service up/down | `up{job="prediction"}` |
| Requêtes/s | `sum(rate(http_requests_total{app="prediction"}[5m]))` |
| Erreurs de prédiction | `sum(rate(prediction_errors_total[5m])) by (reason)` |
| Latence p95 | `histogram_quantile(0.95, sum(rate(prediction_latency_seconds_bucket[5m])) by (le))` |
| Prédictions servies | `sum(rate(prediction_requests_total[5m])) by (result)` |
| Dernier entraînement réussi | `time() - ml_last_successful_training_timestamp` |
| MAE candidat vs baseline vs champion | `ml_last_training_mae`, `ml_baseline_mae`, `ml_champion_mae` |
| Drift détecté | `ml_drift_detected` |
| Score de drift par feature | `ml_drift_score` |
| Promotions / rejets | `ml_model_promotions_total`, `ml_model_rejections_total` |
| Réentraînements déclenchés | `ml_retraining_triggered_total` |
| Version du champion courant | `ml_current_model_info` |

---

## Responsabilités

- **PostgreSQL** = données métier (mesures, historique des prédictions).
- **MLflow** = expérimentations, runs, paramètres, métriques ML, artefacts
  (dont la référence de drift), Model Registry, champion/challenger,
  historique des versions.
- **Prometheus** = métriques techniques et opérationnelles instantanées.
- **Grafana** = visualisation/supervision.
- **Logs** = diagnostic et audit opérationnel détaillé.
- **FastAPI / `prediction`** = exécution et exposition des prédictions
  uniquement — aucune logique métier hors ML/prédiction n'y a été ajoutée.

---

## Configuration

Toutes définies dans `backend/prediction/config.py`
(`PredictionSettings`/`get_settings()`), lues depuis l'environnement avec
valeurs par défaut :

| Variable | Défaut | Rôle |
|---|---|---|
| `MLFLOW_TRACKING_URI` | `http://mlflow:5000` | Serveur MLflow cible |
| `MLFLOW_EXPERIMENT_NAME` | `consumption-prediction` | Expérience MLflow |
| `MLFLOW_MODEL_NAME` | `consumption-predictor` | Registered Model |
| `MIN_IMPROVEMENT_VS_BASELINE` | `0.05` | Amélioration relative minimale vs baseline pour promouvoir |
| `MIN_IMPROVEMENT_VS_CHAMPION` | `0.01` | Amélioration relative minimale vs champion pour promouvoir |
| `DRIFT_THRESHOLD` | `0.2` | Seuil PSI à partir duquel une feature est "en dérive" |
| `MIN_NEW_ROWS` | `1440` | Nombre de nouvelles lignes exploitables déclenchant un réentraînement |

Documentées dans `.env.template`, `.env.local.example`,
`.env.production.example`, et câblées dans `docker-compose.yaml` /
`docker-compose-prod.yaml`. Aucun secret ajouté.

---

## Tests

**Conservés tels quels** (aucune régression) : `test_time_features.py`,
`test_measurement_repository.py`, ainsi que les critères d'acceptation
historiques de `test_dataset.py` et `test_training_service.py` (fixture
MLflow mutualisée dans `conftest.py`, comportement inchangé).

**Ajoutés** (tous isolés d'un vrai serveur MLflow/PostgreSQL — SQLite
temporaire via la fixture `mlflow_tracking_uri` de `conftest.py`, ou mocks) :

| Fichier | Couvre |
|---|---|
| `test_dataset.py` (étendu) | `split_train_val_test`, `clean_dataset` |
| `test_baseline.py` | baseline, MAE, amélioration relative |
| `test_drift_service.py` | PSI, référence, absence/présence de dérive |
| `test_retrain_decision.py` | `should_retrain`, chaque raison isolément et combinée |
| `test_model_registry.py` | alias champion/challenger, promotion/rejet, historique préservé |
| `test_training_pipeline.py` | premier champion, rejet sous baseline, meilleur/pire challenger, historique, drift, logging MLflow |
| `test_prediction_repository.py` | insertion, jointure prédiction/mesure, exclusion des lignes taintées |
| `test_retrain_signals.py` | volume de nouvelles données, performance réelle (avec/sans assez de données) |
| `test_retrain_orchestrator.py` | `train_if_needed` : aucun champion, rien à faire, dérive, volume |
| `test_feature_builder.py` | features du dernier point, historique insuffisant |
| `test_prediction_service.py` | cache champion (charge une fois, recharge sur promotion), prédiction, persistance best-effort |
| `test_api_prediction.py` | 200/404/503/500, `/health`, `/metrics` |
| `test_ml_metrics.py` | compteurs in-process, rafraîchissement des gauges depuis MLflow |
| `test_main.py` (réécrit) | CLI `train`/`train-if-needed`/`serve`, codes de sortie |

**Ajoutés pour le correctif MLflow/artefacts** (mêmes principes
d'isolation ; le cas "artefact inaccessible" est simulé en supprimant
réellement le dossier d'artefacts du backend SQLite isolé de test —
`shutil.rmtree(tmp_path / "artifacts")` — plutôt que par un mock, pour
tester le vrai comportement de `mlflow.sklearn.load_model` face à un
stockage manquant) :

| Test | Couvre |
|---|---|
| `test_training_service.py::test_train_model_logged_model_is_actually_loadable` | l'URI renvoyée par `train_model` pointe vers un artefact réellement rechargeable (§11.A) |
| `test_model_registry.py::test_load_champion_model_raises_champion_load_error_when_artifact_is_unreachable` | champion `READY` mais artefact supprimé → `ChampionLoadError`, pas une `MlflowException` brute qui fuit (§11.D) |
| `test_model_registry.py::test_drift_reference_survives_model_artifact_being_unreachable` | `drift_reference.json` reste récupérable même si le dossier du modèle est perdu — les deux ne partagent pas le même stockage (§10, §11.C) |
| `test_prediction_service.py::test_champion_model_cache_raises_champion_load_error_when_artifact_unreachable` | le cache d'inférence propage `ChampionLoadError` sans la masquer |
| `test_training_pipeline.py::test_broken_champion_does_not_block_training_and_is_recovered` | un champion cassé n'empêche pas un nouvel entraînement ; le candidat qui bat la baseline est promu, tag `recovered_from_broken_champion=true` (§8, §16) |
| `test_training_pipeline.py::test_broken_champion_candidate_still_rejected_if_it_does_not_beat_baseline` | la règle "battre la baseline" reste appliquée même en mode récupération — pas de promotion automatique inconditionnelle |
| `test_retrain_decision.py::test_champion_unavailable_triggers_retrain` | `champion_unavailable` est une raison de réentraînement à part entière |
| `test_retrain_orchestrator.py::test_retrains_and_recovers_when_champion_artifact_is_unreachable` | `train_if_needed` bout-en-bout : détecte, réentraîne, promeut un nouveau champion utilisable |
| `test_api_prediction.py::test_get_prediction_returns_503_when_champion_artifact_is_unreachable` | l'API distingue `ChampionLoadError` de `NoChampionModelError` (logs/métriques) mais retourne `503` dans les deux cas |

**Commandes exactes** :

```bash
# Tests + couverture (identique à la CI)
PYTHONPATH="$PWD/backend/prediction:$PWD/backend" \
  python -m pytest backend/prediction/tests \
  --cov=backend/prediction --cov-report=term-missing --cov-fail-under=80
```

**Résultat réel obtenu dans cet environnement** (venv isolé, dépendances de
`requirements.txt`/`requirements-dev.txt`, aucun serveur MLflow/PostgreSQL
réel) :

```
128 passed
TOTAL coverage: 99.26% (seuil CI : 80%)
```

**Vérification supplémentaire, hors suite pytest** : le vrai code du
service a aussi été exécuté contre un **vrai processus `mlflow server`**
local (`--serve-artifacts --artifacts-destination ...`, MLflow 3.16.0), avec
le répertoire d'artefacts rendu inaccessible au client via un mount
namespace Linux isolé (`unshare --mount` + `tmpfs`) — reproduisant fidèlement
la séparation de filesystem entre conteneurs Docker sans nécessiter Docker.
Résultat réel obtenu :
`mlflow.sklearn.load_model("models:/consumption-predictor@champion")` →
prédiction correcte ; `GET /api/v1/sites/SITE001/prediction` → `200`, corps
JSON correct ; `GET /metrics` → `200`, `ml_current_model_info` reflète la
bonne version. Voir §Troubleshooting pour le mécanisme complet.

---

## Docker

```bash
# Build de l'image
docker build -f backend/prediction/Dockerfile -t enervision-prediction .

# Tests (depuis la racine du repo, venv avec requirements + requirements-dev)
pip install -r backend/prediction/requirements.txt -r backend/prediction/requirements-dev.txt
PYTHONPATH="$PWD/backend/prediction:$PWD/backend" \
  python -m pytest backend/prediction/tests --cov=backend/prediction --cov-fail-under=80

# Entraînement forcé (nécessite Postgres + MLflow accessibles, ex. via docker-compose-data.yaml)
docker compose -f docker-compose.yaml -f docker-compose-data.yaml run --rm prediction \
  python -m prediction.main train

# Vérification automatique (ne réentraîne que si nécessaire)
docker compose -f docker-compose.yaml -f docker-compose-data.yaml run --rm prediction \
  python -m prediction.main train-if-needed

# Service de prédiction (API)
docker compose -f docker-compose.yaml -f docker-compose-data.yaml up -d prediction
curl http://localhost:8003/health
curl http://localhost:8003/api/v1/sites/SITE001/prediction
curl http://localhost:8003/metrics
```

`docker build` n'a **pas** été exécuté dans cet environnement (pas de démon
Docker disponible dans ce sandbox WSL) — **NON VÉRIFIÉ DANS CET
ENVIRONNEMENT**, à valider avec la commande ci-dessus. Les imports Python et
la suite de tests ont en revanche été exécutés et validés (voir §Tests). Le
comportement HTTP-only (aucun partage de filesystem entre `prediction` et
`mlflow`) a lui été vérifié réellement, hors Docker, avec le vrai code du
service — voir §Troubleshooting, "`No such artifact: ''`".

### Healthcheck MLflow et ordre de démarrage

`docker compose run --rm prediction ...` (et `up`) pouvaient démarrer
`prediction` avant que le serveur MLflow n'ait fini son propre démarrage
(connexion au backend store Postgres, montage des routes, etc.), produisant
`Failed to establish a new connection: [Errno 111] Connection refused` sur
`mlflow:5000` — la requête finissait par aboutir seulement parce que le
client MLflow retente automatiquement, un comportement qui masque un vrai
problème d'ordonnancement plutôt que de le résoudre.

Cause : `mlflow` (`docker-compose-data.yaml`) n'avait **aucun healthcheck**,
et `prediction` (`docker-compose.yaml`) ne déclarait `depends_on` que sur
`postgres`, jamais sur `mlflow`.

Correctif, purement Docker Compose (pas de script de retry applicatif) :

```yaml
# docker-compose-data.yaml, service mlflow
healthcheck:
  test:
    [
      "CMD",
      "python",
      "-c",
      "import urllib.request; urllib.request.urlopen('http://localhost:5000/health', timeout=5)",
    ]
  interval: 5s
  timeout: 5s
  retries: 20
  start_period: 15s
```

```yaml
# docker-compose.yaml, service prediction
depends_on:
  postgres:
    condition: service_healthy
  mlflow:
    condition: service_healthy
```

Le test du healthcheck utilise `python -c "import urllib.request; ..."`
plutôt que `curl`/`wget` : l'image officielle `ghcr.io/mlflow/mlflow` ne
garantit pas la présence de ces outils, alors que Python l'est forcément
(c'est le runtime du serveur lui-même) — aucune dépendance supplémentaire
n'est introduite. `mlflow server` expose bien un endpoint `GET /health`
(vérifié : renvoie `200` dès que le serveur a fini de démarrer, dans
l'environnement de test local).

`mlflow` n'étant défini que dans `docker-compose-data.yaml`, ce
`depends_on` ne fonctionne que si `prediction` est démarré avec les deux
fichiers combinés (`-f docker-compose.yaml -f docker-compose-data.yaml`) —
c'est déjà l'unique façon dont ce projet est démarré (`docker.ps1` combine
toujours les deux, comme il le fait déjà pour la dépendance existante
`prediction → postgres`, définie dans le même fichier séparé). `docker
compose run` respecte `depends_on`/`condition: service_healthy` exactement
comme `up`, sauf si `--no-deps` est passé explicitement.

**NON VÉRIFIÉ DANS CET ENVIRONNEMENT** : la syntaxe YAML des deux fichiers a
été validée (`yaml.safe_load`), et le healthcheck a été confirmé
fonctionnel en pointant `mlflow server --host ... --port ...` en dehors de
Docker et en vérifiant `GET /health` en HTTP réel. Le comportement du
`depends_on`/`healthcheck` **dans un vrai `docker compose up`/`run`** n'a
pas pu être exécuté (pas de démon Docker ici) — à vérifier avec :
`docker compose -f docker-compose.yaml -f docker-compose-data.yaml up -d postgres mlflow`
puis `docker compose ... ps` (colonne `STATUS` doit passer à `healthy`
avant que `prediction` ne démarre).

---

## Cycle MLOps complet

```
                       PostgreSQL (ener.measurement)
                           │
                           ▼
                        Dataset (build_dataset)
                           │
                           ▼
                  Features (lag_1h, lag_24h, rolling_mean_24h)
                           │
             ┌─────────────▼─────────────┐
Timer/cron ─►│      train-if-needed      │
             └─────────────┬─────────────┘
                           │
                Drift (PSI vs référence du champion)
                Nouvelles données (vs dataset_max_date champion)
                Performance réelle (ener.prediction ⋈ ener.measurement)
                           │
                     should_retrain
                       ↙       ↘
                     Non       Oui (reasons: no_existing_champion,
                      │              data_drift_detected,
                    Stop            enough_new_data,
                                    real_performance_degraded)
                                    │
                                    ▼
                              run_training_pipeline
                          (split 70/15/15, train, éval,
                           baseline, comparaison champion)
                                    │
                                    ▼
                                  MLflow
                          (run: params/metrics/tags)
                                    │
                              Challenger (register)
                           ↙                    ↘
                     < baseline ou            ≥ seuils
                     < champion                   │
                         │                        ▼
                         ▼                     Champion
                     Rejected              (alias déplacé,
                (historique conservé)     référence drift mise à jour)
                                                   │
                                                   ▼
                                      Prediction Service
                                    (ChampionModelCache, cache
                                     jusqu'à nouvelle promotion)
                                                   │
                                                   ▼
                                    GET /api/v1/sites/{id}/prediction
                                                   │
                                                   ▼
                                          Frontend (autre équipe,
                                           non modifié ici)
```

Observabilité :

```
Training ─────┐
Prediction ───┼──► Logs (logging structuré, extra={...})
Drift ────────┤
MLflow ops ───┘

Training ─────┐
Prediction ───┼──► Prometheus (in-process + gauges recalculées depuis MLflow) ───► Grafana
Drift ────────┘
```

---

## Troubleshooting

### `mlflow.exceptions.MlflowException: No such artifact: ''`

**Symptôme** : levée en chargeant le champion
(`mlflow.sklearn.load_model("models:/consumption-predictor@champion")`),
typiquement observée comme un `503`/`500` sur
`GET /api/v1/sites/{site_id}/prediction`, ou une erreur interrompant
`python -m prediction.main train` en tentant de charger le champion
existant pour comparaison.

**Cause** : l'expérience MLflow dans laquelle vit le run du champion a un
`artifact_location` en chemin filesystem brut (ex. `/mlflow-artifacts/1`)
plutôt qu'en schéma proxifié (`mlflow-artifacts:/1`). Le conteneur qui
essaie de charger le modèle n'a pas ce chemin monté sur son propre
filesystem (normal : seul le conteneur `mlflow` a accès au volume
`/mlflow-artifacts`) → le `LocalArtifactRepository` côté client ne trouve
rien. Voir §MLflow — Architecture des artefacts pour le mécanisme complet.

**Diagnostic** :

```bash
docker compose -f docker-compose.yaml -f docker-compose-data.yaml exec mlflow \
  python -c "
import mlflow
mlflow.set_tracking_uri('http://localhost:5000')
exp = mlflow.get_experiment_by_name('consumption-prediction')
print(exp.artifact_location)
"
```

- Commence par `mlflow-artifacts:/` → configuration serveur saine, le
  problème est ailleurs (vérifier que le champion pointe vers un run réel :
  `client.get_model_version_by_alias('consumption-predictor', 'champion')`,
  puis `client.list_artifacts(run_id)` / le contenu du `LoggedModel`
  associé).
- Commence par `/` (chemin brut) → expérience créée avant le correctif de
  la commande `mlflow server` (voir `docker-compose-data.yaml` :
  `--artifacts-destination` + `--serve-artifacts`, jamais
  `--default-artifact-root <chemin brut>`). **Remédiation** : définir
  `MLFLOW_EXPERIMENT_NAME=consumption-prediction-v2` (ou un autre nom neuf)
  dans `.env`/`.env.local`, puis relancer `python -m prediction.main train`
  — une expérience saine est créée automatiquement, l'ancienne reste
  intacte et consultable dans l'UI MLflow.

Dans l'intervalle (champion existant mais cassé, avant remédiation), le
service ne reste pas bloqué indéfiniment : `python -m prediction.main train`
et `train-if-needed` détectent l'échec de chargement
(`registry.ChampionLoadError`), le journalisent
(`event=champion_unavailable`) et promeuvent un nouveau champion dès qu'un
candidat bat la baseline, taggé `recovered_from_broken_champion=true` —
voir §MLflow — Robustesse champion cassé.

### `Failed to establish a new connection: [Errno 111] Connection refused` (`mlflow:5000`)

**Symptôme** : au démarrage de `prediction` (via `docker compose run` ou
`up`), quelques tentatives échouent avant que le training/l'API ne
fonctionne normalement.

**Cause** : `mlflow` prend le temps de démarrer réellement (connexion à son
backend store Postgres, initialisation du serveur ASGI) ; sans
`depends_on: condition: service_healthy`, Compose démarre `prediction` dès
que `postgres` est prêt, sans attendre `mlflow`. Voir §Docker — Healthcheck
MLflow et ordre de démarrage pour le correctif appliqué
(`healthcheck` sur `mlflow` + `depends_on: mlflow: condition: service_healthy`
sur `prediction`).

**Vérification** :

```bash
docker compose -f docker-compose.yaml -f docker-compose-data.yaml ps mlflow
# STATUS doit afficher "healthy", pas juste "Up"
docker compose -f docker-compose.yaml -f docker-compose-data.yaml logs mlflow | tail -50
```

Si le problème persiste après le correctif : vérifier que l'image
`mlflow` a bien été reconstruite (`docker compose ... build mlflow`) après
la mise à jour de `docker-compose-data.yaml`, et que le `start_period`
(15 s) est suffisant sur la machine cible (l'augmenter si le serveur met
plus longtemps à répondre à `/health` au premier démarrage).

---

## Limitations

- **Volume/qualité des données** : ce travail a été développé et testé avec
  des jeux de données **synthétiques déterministes** dans les tests
  (relations linéaires construites pour valider la logique d'orchestration
  et de décision), pas avec le volume réel de production. Le comportement
  du drift PSI et des seuils par défaut (`DRIFT_THRESHOLD=0.2`,
  `MIN_NEW_ROWS=1440`) devra être **validé avec des données réelles** avant
  mise en production — ces valeurs sont des points de départ raisonnables,
  pas des constantes calibrées sur le trafic réel du service.
- **`LinearRegression`** : modèle volontairement simple, ne capture pas de
  non-linéarités (saisonnalité intra-journalière, effets calendaires). Le
  besoin demandait explicitement de le conserver — l'industrialisation
  autour, pas le remplacement, était l'objectif.
- **Drift (PSI)** : sensible au nombre de bins (10, fixe) et à la référence
  choisie (train du champion) ; une dérive lente et progressive sur
  plusieurs entraînements successifs sans jamais dépasser le seuil en une
  fois pourrait passer inaperçue. Une seule feature en dérive suffit à
  déclencher un réentraînement — potentiellement plus sensible que
  nécessaire selon le contexte métier réel (`DRIFT_THRESHOLD` est
  configurable pour ajuster).
- **Baseline** : `lag_1h` est une baseline volontairement simple ; elle ne
  capture pas la saisonnalité journalière (`lag_24h` seul pourrait parfois
  faire mieux). C'est un choix du besoin, pas une limite technique du code.
- **Performance réelle récente** : disponible seulement une fois que
  `ener.prediction` contient au moins 30 prédictions dont l'horizon cible
  est passé et dont la mesure réelle correspondante est arrivée et fiable
  (non taintée). **Juste après le déploiement de cette fonctionnalité, ce
  signal sera systématiquement absent** (`real_performance=None`) — c'est
  attendu et documenté, pas une erreur silencieuse.
- **Pas d'embargo** autour des cutoffs du split train/validation/test
  (comportement hérité de l'implémentation EN-263 existante, assumé pour ce
  volume de données).
- **Ordonnancement réel** : la procédure cron/systemd fournie (§Automatisation)
  n'a pas pu être installée ni vérifiée sur un serveur réel dans cet
  environnement — seule la partie applicative (les sous-commandes CLI) a
  été testée.
- **Docker build / `docker compose up` réel** : non exécuté dans cet
  environnement (pas de démon Docker disponible dans ce sandbox WSL) — le
  `depends_on`/`healthcheck` de §Docker n'a donc pas pu être observé dans un
  vrai `docker compose up`, seulement validé syntaxiquement (YAML) et par le
  raisonnement (le même pattern `depends_on` cross-fichier est déjà utilisé
  avec succès par `prediction → postgres`).
- **Le mécanisme HTTP-only des artefacts, lui, a été vérifié réellement**
  hors Docker : un vrai `mlflow server --serve-artifacts --artifacts-destination ...`
  a été lancé en local, le vrai code de `backend/prediction`
  (`training_service.train_model`, `model_registry.register_challenger` /
  `promote_to_champion` / `load_champion_model`, `PredictionService`,
  l'API FastAPI complète via `TestClient`) a tourné contre ce serveur, et le
  chargement du champion + `GET /api/v1/sites/{id}/prediction` +
  `GET /metrics` ont été exécutés depuis un processus dont le répertoire
  d'artefacts était rendu vide via un mount namespace Linux dédié (`unshare
  --mount` + `tmpfs`) — une simulation fidèle de "un conteneur sans accès
  au volume `/mlflow-artifacts` d'un autre conteneur", sans avoir besoin de
  Docker lui-même pour le démontrer. Cela reste néanmoins une simulation :
  le comportement réseau réel entre conteneurs Docker sur
  `enervision_network` n'a pas été observé.
- **Postgres réel** : `ener.prediction`/`ener.measurement` n'ont pas été
  testés contre une vraie instance PostgreSQL dans cet environnement — les
  tests utilisent des mocks/fixtures pour `prediction_repository.py` (voir
  §Tests). La requête SQL de jointure (§Réentraînement — Performance réelle)
  n'a donc pas été exécutée contre un vrai moteur SQL.
- **Expériences MLflow pré-existantes** : si l'expérience
  `consumption-prediction` de votre déploiement réel a été créée avant ce
  correctif, elle reste **définitivement** non proxifiée (voir §MLflow —
  Architecture des artefacts) ; je n'ai pas accès à votre backend store
  MLflow réel pour vérifier son état actuel — utilisez la commande de
  diagnostic donnée en §Troubleshooting.
