# Observabilité — métriques et logs

Prometheus collecte les **métriques**, Loki collecte les **logs**, Grafana affiche
les deux. Ce dossier contient toute la configuration.

| Service | Rôle | Port interne |
|---|---|---|
| `prometheus` | métriques (requêtes, latence, ressources) | 9090 |
| `loki` | stockage et recherche des logs | 3100 |
| `promtail` | lit les logs Docker et les envoie à Loki | 9080 |
| `grafana` | interface de consultation et d'alerte | 3000 |
| `node-exporter` | métriques de l'hôte Linux | 9100 |
| `cadvisor` | métriques par conteneur | 8080 |

Les sources de données Prometheus et Loki sont créées automatiquement au
démarrage de Grafana, via `grafana/provisioning/datasources/datasources.yml`.
Il n'y a rien à saisir à la main dans l'interface.

---

## Démarrer

### En production

```bash
cd observability
docker compose up -d
```

La stack d'observabilité **n'est pas déployée par la pipeline CI/CD** : elle se
lance à la main sur le serveur. Elle n'a pas besoin d'être redéployée quand
l'applicatif change.

### En local

```bash
cd observability
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

L'override local publie les ports (Grafana 3000, Prometheus 9090, Loki 3100),
désactive l'authentification Grafana et remplace le réseau Traefik par un réseau
créé à la volée. `node-exporter` y est désactivé : il mesure un hôte Linux et ne
démarre pas sur macOS.

Grafana est alors sur <http://127.0.0.1:3000>.

---

## Les logs applicatifs

Les trois services Python écrivent en **JSON**, une ligne par événement. Grafana
peut donc filtrer sur des champs plutôt que de chercher du texte à la regex —
ce qui évite les faux positifs, un numéro de port à quatre chiffres ressemblant
à un code HTTP quand on ne lit que du texte.

La configuration est partagée : `backend/shared/logging_setup.py`.

### Brancher un service sur ces logs

Un seul appel, **avant tout autre import du service** :

```python
from shared.logging_setup import setup_logging

setup_logging("core")   # ou "etl", "worker-ingestion"
```

L'ordre n'est pas cosmétique. `setup_logging` remplace les gestionnaires du
logger racine ; les loggers créés **ensuite** en héritent. Un module importé
avant l'appel installerait sa propre configuration — c'est le cas d'uvicorn —
et ses lignes ressortiraient en texte brut au milieu du JSON.

Dans `backend/core/main.py`, l'appel est donc placé au-dessus des imports de
contrôleurs, ce qui déroge à l'usage de regrouper les imports en tête de
fichier. C'est volontaire, et le commentaire dans le code l'explique.

L'argument passé à `setup_logging` devient l'étiquette `service` de chaque
ligne : c'est elle qui permet d'écrire `{service="etl"}` dans Grafana. Elle est
ajoutée automatiquement, il n'y a jamais à la répéter dans les appels.

### Ajouter des champs à un log

N'importe quel logger du service produit désormais du JSON. Pour y joindre des
champs métier, utiliser `extra` :

```python
logger.info(
    "Lot validé : %d fichier(s), %d mesure(s)",
    fichiers, mesures,
    extra={"event": "etl.lot_valide", "fichiers": fichiers, "mesures": mesures},
)
```

Le message reste lisible dans `docker logs`, et les champs deviennent
interrogeables dans Grafana (`| json | mesures > 0`).

Conserver le champ `event` sur les événements métier : c'est lui qui sert de
point d'accroche aux requêtes et aux alertes, plutôt qu'une recherche de texte
dans le message — un message se reformule, un `event` non.

### Champs communs à toutes les lignes

| Champ | Exemple |
|---|---|
| `timestamp` | `2026-09-09T11:29:35.427465+00:00` |
| `level` | `INFO`, `WARNING`, `ERROR` |
| `service` | `core`, `etl`, `worker-ingestion` |
| `logger` | `core.request` |
| `message` | texte lisible |

### Champs propres aux requêtes HTTP (`core`)

Posés par `backend/core/api/middleware/request_logging.py`, une ligne par requête.

| Champ | Exemple |
|---|---|
| `method` | `GET` |
| `path` | `/api/v1/backend/alerts` |
| `status` | `404` |
| `duration_ms` | `17.7` |
| `query` | `site_id=INCONNU` |
| `request_id` | `86601184a025` |

Le niveau suit le statut : **`ERROR` pour les 5xx**, **`WARNING` pour les 4xx**,
`INFO` sinon. `/health` et `/metrics` ne sont pas journalisés — le scrape
Prometheus toutes les 15 s noierait tout le reste.

Le `request_id` est aussi renvoyé au client dans l'en-tête `X-Request-ID` :
quand quelqu'un signale une erreur, il peut donner cet identifiant et on
retrouve la requête exacte.

### Le middleware de requêtes (`core`)

`backend/core/api/middleware/request_logging.py` produit **une ligne par
requête HTTP**. C'est un middleware Starlette : il enveloppe chaque appel,
mesure sa durée et journalise son issue, sans qu'aucun contrôleur n'ait à s'en
soucier.

Il est branché dans `backend/core/main.py` :

```python
app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(CORSMiddleware, ...)
```

**L'ordre compte.** Les middlewares s'exécutent dans l'ordre inverse de leur
ajout : celui déclaré en premier enveloppe tous les autres. En le plaçant avant
le CORS, il voit le statut réellement renvoyé au client, y compris quand une
autre couche modifie la réponse.

Ce qu'il fait, dans l'ordre :

1. **Attribue un `request_id`** — celui de l'en-tête `X-Request-ID` s'il existe,
   sinon un identifiant court généré. Il est posé sur `request.state` (donc
   accessible depuis les contrôleurs) et renvoyé au client dans l'en-tête de
   réponse. Quand quelqu'un signale une erreur, il peut citer cet identifiant.
2. **Chronomètre** la requête (`duration_ms`).
3. **Choisit le niveau** selon le statut : `ERROR` pour les 5xx, `WARNING` pour
   les 4xx, `INFO` sinon. C'est ce qui rend `| json | level = "ERROR"`
   exploitable pour une alerte.
4. **Trace les exceptions** non rattrapées avec leur pile d'appel, puis les
   relaie telles quelles — le middleware observe, il n'avale rien.

`/health` et `/metrics` sont exclus (`CHEMINS_IGNORES`) : la sonde Docker toutes
les 15 s et le scrape Prometheus noieraient tout le reste.

**Pourquoi un middleware plutôt que des logs dans chaque contrôleur** : aucune
route ne peut être oubliée, y compris celles qui échouent avant d'atteindre leur
contrôleur — un 422 de validation, un 404 de route inconnue. Ces cas-là sont
précisément ceux qu'on veut voir.

Pour ajouter une autre préoccupation transversale (limitation de débit, en-têtes
de sécurité), c'est le même dossier `middleware/` et le même branchement.

### Événements métier

| `event` | Service | Champs |
|---|---|---|
| `etl.blobs_listes` | etl | `blobs`, `lookback_minutes` |
| `etl.lot_valide` | etl | `fichiers`, `mesures` |
| `etl.alertes_a_lire` | etl | `blobs`, `deja_traites`, `a_lire` |
| `etl.cycle_echec` | etl | `phase` (`mesures` / `alertes`) |
| `etl.heartbeat` | etl | `mesures_ok`, `alertes_ok`, `duration_ms` |
| `worker.lecture_archivee` | worker-ingestion | `site_id`, `data_quality`, `blob` |
| `worker.alertes_archivees` | worker-ingestion | `alertes`, `blob` |
| `worker.cycle_echec` | worker-ingestion | `phase` |
| `worker.heartbeat` | worker-ingestion | `mesures_ok`, `alertes_ok`, `duration_ms` |

---

## Requêtes utiles

Dans Grafana : **Explore** → source **Loki** → onglet **Code**.

```logql
# Pannes de l'API
{service="core"} | json | status >= 500

# Appels incorrects (404, 422, 401)
{service="core"} | json | status >= 400

# Requêtes lentes
{service="core"} | json | duration_ms > 500

# Suivre une requête précise de bout en bout
{service="core"} | json | request_id = "86601184a025"

# Chaque cycle d'ingestion et son volume
{service="etl"} | json | event = "etl.lot_valide"

# Pertes de connexion (Azure, Mock API, base)
{service="etl"} | json | event = "etl.cycle_echec"
{service="worker-ingestion"} | json | event = "worker.cycle_echec"

# Toutes les erreurs, tous services confondus
{service=~"core|etl|worker-ingestion"} | json | level = "ERROR"
```

---

## Healthchecks des conteneurs

Chaque service applicatif porte une sonde qui dit à Docker s'il fonctionne.
`docker ps` affiche alors `(healthy)` ou `(unhealthy)` au lieu du simple `Up`.

| Service | Sonde | Fenêtre |
|---|---|---|
| `core` | requête HTTP sur `/health` | 15 s |
| `frontend` | requête HTTP sur `/_stcore/health` (sonde native Streamlit) | 15 s |
| `etl` | fraîcheur du battement de cœur | 10 min |
| `worker-ingestion` | fraîcheur du battement de cœur | 5 min |
| `postgres` | `pg_isready` | 5 s |
| `keycloak` | requête HTTP sur `/health/ready` (port 9000) | 5 s |

### Les sondes sont dans les Dockerfiles, pas dans le compose

C'est délibéré : **`deploy.sh` déploie avec `docker run`, pas avec
`docker compose`**. Une sonde écrite dans `docker-compose.yaml` serait donc
ignorée en production. Placée dans le Dockerfile, elle voyage avec l'image et
s'applique partout.

Les images `slim` n'embarquent pas `curl` : les sondes HTTP passent par
`urllib`, Python étant de toute façon présent.

### Le heartbeat de l'ETL et du worker

Ces deux services sont des boucles, pas des serveurs : il n'y a aucun port à
interroger pour savoir s'ils vont bien.

À la fin de chaque cycle, ils écrivent l'heure courante dans un fichier
(`/tmp/heartbeat` par défaut, `HEARTBEAT_FILE` pour en changer). La sonde
vérifie simplement que ce fichier est récent.

Le code tient en deux fonctions, dans `backend/shared/heartbeat.py` :
`touch()` à la fin du cycle, `est_frais(secondes)` dans la sonde.

**Pourquoi ce détour plutôt que vérifier que le processus tourne** : un service
figé — bloqué sur une connexion Azure qui ne répond jamais — garde son
conteneur `Up` alors qu'il ne fait plus rien. Le fichier, lui, cesse d'être mis
à jour, et la panne devient visible.

La fenêtre de l'ETL est large (10 min) parce qu'un cycle de rattrapage peut
durer plusieurs minutes. Mieux vaut rater une panne brève que redémarrer en
boucle un service qui travaille.

Le même battement de cœur est aussi émis en log (`etl.heartbeat`,
`worker.heartbeat`) : le fichier sert à Docker, le log sert à Grafana.

### Tester qu'une sonde détecte bien une panne

```bash
# Supprimer le battement de cœur de l'ETL
docker exec enervisionapplicatif-etl-1 rm /tmp/heartbeat

# Après ~3 minutes (3 échecs à 60 s)
docker ps        # -> unhealthy
```

L'ETL repasse `healthy` tout seul au cycle suivant, quand le fichier est
réécrit. Aucune intervention n'est nécessaire.

### Ce qu'un healthcheck ne fait pas

Il informe, il ne répare pas. Docker ne redémarre **pas** un conteneur
`unhealthy` — `restart: unless-stopped` ne réagit qu'à l'arrêt du processus.
C'est pour cela que les alertes Grafana décrites plus bas restent nécessaires :
elles, elles préviennent quelqu'un.

---

## Configurer les alertes dans Grafana

### 1. Le point de contact (mail)

Le SMTP se configure par variables d'environnement sur le conteneur Grafana,
dans `docker-compose.yml` :

```yaml
  grafana:
    environment:
      GF_SMTP_ENABLED: "true"
      GF_SMTP_HOST: smtp.example.com:587
      GF_SMTP_USER: ${SMTP_USER}
      GF_SMTP_PASSWORD: ${SMTP_PASSWORD}
      GF_SMTP_FROM_ADDRESS: enervision@example.com
      GF_SMTP_FROM_NAME: EnerVision
```

Redémarrer Grafana, puis : **Alerting → Contact points → Add contact point**,
type **Email**, saisir les destinataires, et **Test** pour vérifier.

> Ne pas écrire le mot de passe SMTP dans le fichier : passer par une variable
> d'environnement ou un secret Docker, comme le reste du projet.

### 2. Les règles d'alerte

**Alerting → Alert rules → New alert rule.** Source de données : **Loki**.

#### a. L'API renvoie des erreurs

```logql
sum(count_over_time({service="core"} | json | status >= 500 [5m]))
```

Condition : `IS ABOVE 5`. Évaluation toutes les minutes, `pending period` 5 min
pour ne pas alerter sur un pic isolé.

#### b. L'ETL est mort — **la plus importante**

```logql
sum(count_over_time({service="etl"} | json | event = "etl.heartbeat" [10m]))
```

Condition : `IS BELOW 1`.

C'est **l'absence** de log qui alerte. Un service planté n'écrit aucune erreur :
une alerte fondée sur les erreurs ne le verrait jamais. Le battement de cœur est
émis à chaque cycle, même quand le cycle échoue.

#### c. Le worker d'ingestion est mort

Même règle avec `{service="worker-ingestion"}` et `event = "worker.heartbeat"`.
Adapter la fenêtre à `POLL_INTERVAL_SECONDS`.

#### d. Perte de connexion Azure ou Mock API

```logql
sum(count_over_time({service=~"etl|worker-ingestion"} | json | event =~ ".*cycle_echec" [10m]))
```

Condition : `IS ABOVE 0`.

---

## À faire en production

### Reconstruire les images applicatives

`backend/shared/logging_setup.py` est **copié dans les images** au moment du
build, il n'est pas monté. Une image construite avant ce changement plante au
démarrage :

```
ModuleNotFoundError: No module named 'shared.logging_setup'
```

Les images de `core`, `etl` et `worker-ingestion` doivent donc être
reconstruites et republiées avant d'être déployées. La pipeline s'en charge dès
que ces dossiers changent.

### Niveau de log

`LOG_LEVEL` (défaut `INFO`) pilote les trois services. En cas de besoin,
`DEBUG` sur un service, jamais en permanence : le volume de logs explose et la
rétention Loki tombe à quelques heures.

### Rétention et disque

Loki conserve **14 jours** (`retention_period: 336h` dans `loki/loki.yml`) et
stocke sur le volume `loki_data`. Surveiller l'espace disque du serveur : c'est
la seule limite réelle. Réduire la rétention si nécessaire.

### Réseaux

`prometheus` et `grafana` sont sur `observability` **et** `traefik_network`
(réseau externe `g3_default`). `loki` et `promtail` restent sur `observability`
seulement : ils n'ont pas à être joignables de l'extérieur.

Grafana est exposé via `traefik/dynamic.yml`
(`grafana.enervisiong3.prod` → `http://grafana:3000`), pas par des labels
Docker — Traefik tourne avec le provider fichier uniquement.

### Accès Grafana

En production, **ne pas activer l'accès anonyme** : c'est réservé à l'override
local. Le mot de passe administrateur se définit par
`GF_SECURITY_ADMIN_PASSWORD`.

### Socket Docker

Promtail monte `/var/run/docker.sock` en lecture seule pour découvrir les
conteneurs et lire leurs sorties. C'est un accès privilégié : ne pas exposer ce
conteneur, et le laisser sur le réseau `observability`.

### Prometheus et les autres services

`prometheus/prometheus.yml` ne collecte que `core`. L'ETL et le worker n'ont pas
d'endpoint `/metrics` : ce ne sont pas des serveurs HTTP. Leur suivi passe
aujourd'hui par les logs. Les instrumenter avec `prometheus_client` est un
chantier séparé.
