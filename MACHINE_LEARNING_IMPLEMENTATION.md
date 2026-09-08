# Machine Learning / MLOps — EnerVision

Documentation du cycle MLOps du service `backend/prediction/` : dataset,
entraînement, baseline, drift, promotion champion/challenger, service
d'inférence, API, observabilité. Base légale : `LinearRegression`
(`sklearn.linear_model.LinearRegression`) sur les trois features existantes
(`lag_1h`, `lag_24h`, `rolling_mean_24h`), inchangées.

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
- **`retrain/signals.py`** fournit les deux entrées "réelles" que la config
  seule ne peut pas donner :
  - `count_new_rows_since_champion` — compte les lignes de
    `clean_dataset(df)` postérieures à `dataset_max_date`, un **paramètre**
    loggé sur **chaque** run d'entraînement (`training/pipeline.py`) avec la
    date la plus récente du dataset utilisé.
  - `compute_real_performance` — voir section suivante.
- **`retrain/orchestrator.train_if_needed()`** enchaîne : construire le
  dataset → chercher le champion → calculer le drift (test set) → calculer
  les deux signaux → `should_retrain(...)` → logger la décision → **ne rien
  faire** si `should_retrain=False`, sinon appeler
  `training.pipeline.run_training_pipeline(trigger_source="cli_train_if_needed",
  retrain_reasons=decision.reasons)`.

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
    (`register_challenger`) — jamais automatiquement via
    `registered_model_name` sur `log_model` (voir §Modèle) — puis
    **explicitement** promue (alias `champion`, ancien alias `challenger`
    retiré) ou rejetée (alias `challenger` retiré, tags `rejected=true`).
    **Aucune version n'est jamais supprimée** : promotion/rejet ne touchent
    que des alias et des tags.
- **Champion/Challenger** : implémenté avec les **alias** du Model Registry
  (`client.set_registered_model_alias`, `get_model_version_by_alias`,
  `delete_registered_model_alias` — API moderne, pas les *stages* dépréciés).
  `registry/model_registry.py` centralise ces appels.
- **Promotion/rejet** — logique dans `training/pipeline._decide_promotion` :
  1. Si `mae_improvement_vs_baseline < MIN_IMPROVEMENT_VS_BASELINE` → **rejet**,
     quel que soit le champion.
  2. Sinon, si aucun champion n'existe → **promotion** (premier champion).
  3. Sinon, si `mae_improvement_vs_champion >= MIN_IMPROVEMENT_VS_CHAMPION` →
     **promotion** (le champion actuel est remplacé).
  4. Sinon → **rejet**, champion inchangé.
- **Historique** : `tests/test_training_pipeline.py::test_history_of_all_versions_is_preserved`
  vérifie explicitement qu'après deux promotions successives, la première
  version reste consultable via `client.get_model_version(...)`.

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
  `404` si historique insuffisant, `503` si aucun champion disponible,
  `500` sur toute autre erreur (loggée).

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
| `prediction_errors_total` | Counter | `reason` | in-process |
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
118 passed
TOTAL coverage: 99.21% (seuil CI : 80%)
```

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
la suite de tests ont en revanche été exécutés et validés (voir §Tests).

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
- **Docker build** : non exécuté dans cet environnement (pas de démon Docker
  disponible) — voir §Docker pour la commande de vérification.
- **Cycle MLflow bout-en-bout contre un vrai serveur MLflow/PostgreSQL de
  production** : non vérifié ici (uniquement testé contre un backend SQLite
  local isolé, par construction, pour ne jamais dépendre d'une
  infrastructure réelle dans les tests unitaires) — voir §Tests pour la
  commande à rejouer contre l'environnement réel une fois déployé.
