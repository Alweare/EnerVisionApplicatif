# EnerVision

Supervision de la consommation énergétique des sites : ingestion, ETL, API et dashboard.

## Architecture

```
Utilisateur
    │
    ▼
Frontend Streamlit (frontend/)
    │  st.login() → redirection navigateur
    ▼
Keycloak (infra existante, hors de ce repo)
    │  Authorization Code Flow (OIDC)
    ▼
Frontend Streamlit (session authentifiée)
    │  Authorization: Bearer <access_token>
    ▼
backend/core (API FastAPI, backend/main.py)
    │  validation JWT locale (JWKS Keycloak)
    ▼
Données protégées
```

`backend/core` est l'API qui sert le frontend — ce n'est pas une librairie
partagée. Chaque package sous `backend/` qui a un point d'entrée (`main.py`)
est un conteneur indépendant, avec son propre `Dockerfile` :
`workeringestion` et `health` en plus de `backend`/`core`. `etl`, `sites`,
`consumption`, `prediction`, `recommendation` n'ont pour l'instant ni
`main.py` ni `Dockerfile` : ce sont du code utilisé par d'autres services
(ex. `etl` par `workeringestion`), pas encore des services à part entière.
`backend/authentication` est un dossier vide, sans usage actuel.

## Authentification

Les identifiants (login / mot de passe) sont saisis **uniquement sur
Keycloak**. Le frontend Streamlit ne reçoit et ne stocke jamais le mot de
passe : il utilise le support natif OpenID Connect de Streamlit
(`st.login()` / `st.logout()` / `st.user`), qui délègue tout le flux OAuth2
Authorization Code à Keycloak.

- `frontend/authentification/auth.py` : `require_authentication()` bloque
  l'accès au dashboard tant que l'utilisateur n'est pas connecté (bouton
  "Se connecter" → `st.login()`) ; `render_user_menu()` affiche l'identité
  et un bouton de déconnexion.
- `frontend/services/api_client.py` : centralise les appels HTTP vers
  `backend/core`, en attachant automatiquement `Authorization: Bearer
  <access_token>` (récupéré via `st.user.tokens["access"]`), et gère les
  cas d'erreur (backend indisponible, session expirée → déconnexion).
- `backend/core/security.py` : valide localement les access tokens
  Keycloak (signature, expiration, issuer, audience) via les clés
  publiques JWKS du realm, récupérées par découverte OIDC
  (`/.well-known/openid-configuration`) et mises en cache — Keycloak
  n'est pas recontacté à chaque requête.
- `GET /api/v1/me` (`backend/core/api/routes.py`) : endpoint protégé qui
  retourne l'identité extraite du token. Sert à vérifier de bout en bout
  que le frontend transmet bien un token accepté par l'API.

Cette US couvre l'**authentification** (qui est l'utilisateur), pas
l'autorisation. Les rôles Keycloak sont déjà extraits par
`backend/core/security.get_current_user` (champ `roles`) pour permettre
une gestion des droits (RBAC) dans une US ultérieure, sans rien avoir à
recâbler.

## Variables d'environnement

Deux environnements, deux fichiers, chaque variable définie une seule fois :

| Fichier (exemple, versionné) | Copier en | Utilisé par |
|---|---|---|
| `.env.local.example` | `.env.local` | `.\docker.ps1 local ...` |
| `.env.production.example` | `.env` | `docker compose up -d` (chargé automatiquement par Compose) |

```powershell
Copy-Item .env.local.example .env.local
Copy-Item .env.production.example .env   # à remplir avec les vraies valeurs de prod
```

| Variable | Où | Description |
|---|---|---|
| `KEYCLOAK_URL` | backend | URL de Keycloak joignable **depuis les conteneurs** (local : `http://keycloak:8080` ; prod : instance distante) |
| `KEYCLOAK_REALM` | backend | Realm Keycloak (ex: `enervision`) |
| `KEYCLOAK_CLIENT_ID` | backend | Audience attendue dans les access tokens (client API, ex: `enervision-api`) |
| `BACKEND_URL` | frontend | URL de `backend/core` joignable depuis le conteneur frontend (ex: `http://backend:8000`) |
| `APP_ENVIRONMENT` | backend | `development` en local, `production` en prod (cosmétique côté app, ne pilote pas Compose) |

`frontend/.env.template` reste disponible pour lancer le frontend hors Docker.

## Secrets

Aucun secret n'est commité ni hardcodé.

- Backend : `secrets/db_password` et `secrets/keycloak_client_secret`
  (fichiers Docker secrets, gitignorés, montés dans `/run/secrets`). Le
  dossier `secrets/` n'est pas versionné : le créer localement et y écrire
  la valeur brute (pas de `KEY=value`, juste le secret) dans chaque
  fichier, par ex. `echo -n "<client secret Keycloak>" > secrets/keycloak_client_secret`.
- Frontend : `frontend/.streamlit/secrets.toml` (gitignoré). Copier
  `frontend/.streamlit/secrets.toml.example`, puis renseigner :
  - `client_id` / `client_secret` : client Keycloak `enervision-frontend`
    (voir *Configuration Keycloak* ci-dessous) ;
  - `cookie_secret` : générer avec
    `python -c "import secrets; print(secrets.token_hex(32))"` ;
  - `redirect_uri` : URL absolue du frontend + `/oauth2callback`.

## Mode local vs mode production

```text
docker compose up -d                =  PRODUCTION
                                        (backend, health, frontend,
                                         worker-ingestion uniquement ; pas
                                         de Keycloak/Traefik locaux ; pas
                                         de --reload)

.\docker.ps1 local up -d            =  LOCAL
                                        (+ PostgreSQL, Keycloak local,
                                         Traefik local, hot-reload, bind
                                         mounts du code)
```

Le fichier `docker-compose.yaml` (utilisé seul, sans `-f`) est la base
commune, sûre par défaut pour un déploiement distant : aucune dépendance
à Keycloak/Traefik locaux, pas de bind mount ni de `--reload`. Le mode
local ajoute des fichiers Compose séparés via `-f`, jamais fusionnés
manuellement :

| Fichier | Rôle | Utilisé en prod ? |
|---|---|---|
| `docker-compose.yaml` | services applicatifs (base) | Oui (seul) |
| `docker-compose-postgres.yaml` | PostgreSQL + migrations | Non |
| `docker-compose-keycloak.yaml` | Keycloak local | Non |
| `docker-compose-traefik.yml` | Traefik local (HTTPS) | Non |
| `docker-compose.local.yml` | hot-reload, bind mounts, réseau non-externe | Non |

`docker-compose.yaml` **n'est pas** le pipeline de déploiement CI/CD : le
déploiement réel (`deploy.sh`, sur le serveur) cible `docker-compose-prod.yaml`
(images GHCR, par service), géré séparément. Ce README documente la
configuration à utiliser depuis un poste développeur.

### `docker.ps1` — sélecteur léger

`docker.ps1` ne fait que choisir `--env-file` + la liste de `-f` puis
transmet le reste tel quel à `docker compose` (aucune logique
supplémentaire) :

```powershell
.\docker.ps1 local up -d       # démarre toute la stack locale
.\docker.ps1 local down        # arrête
.\docker.ps1 local down -v     # arrête ET repart de zéro (efface les volumes : DB, realm Keycloak)
.\docker.ps1 local ps
.\docker.ps1 local logs -f backend

.\docker.ps1 prod up -d        # équivalent explicite de : docker compose up -d
```

### Keycloak local (développement uniquement)

Pour développer/tester l'authentification sans dépendre du Keycloak de
staging/production, un Keycloak conteneurisé **local** est disponible via
`docker-compose-keycloak.yaml`, inclus automatiquement par
`.\docker.ps1 local ...`. Il n'est **jamais** utilisé en
staging/production (Keycloak y reste géré indépendamment de ce repo) et ne
modifie aucune instance distante.

Le realm `enervision`, les clients `enervision-frontend` /
`enervision-api` et un utilisateur de test sont importés automatiquement
au démarrage depuis `keycloak/realm-export.json` — aucune configuration
manuelle dans la console n'est nécessaire pour le local.

**Utilisateur de test local** (réservé au dev, non sensible) :
`test` / `test`.

**Compte admin Keycloak local** (console `http://localhost:8080/admin`) :
`admin` / `admin` — défini dans `docker-compose-keycloak.yaml`, jamais
réutilisé ailleurs.

**Client secrets locaux** (dev uniquement, versionnés dans
`keycloak/realm-export.json` car non sensibles — jamais ceux de
staging/production) : `enervision-frontend` → `local-dev-frontend-secret`,
`enervision-api` → `local-dev-api-secret`.

### Résolution hostname navigateur vs conteneur

Keycloak est configuré avec `KC_HOSTNAME=http://localhost:8080` (fixe,
utilisé pour l'`issuer` et l'URL d'autorisation, donc visible et
cohérent pour le navigateur) et `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true` :
les endpoints serveur-à-serveur (token, JWKS, userinfo) se résolvent
dynamiquement selon l'URL réellement utilisée pour joindre Keycloak. Le
frontend et `backend/core`, qui l'appellent via `http://keycloak:8080`
(réseau Docker), reçoivent donc des endpoints backchannel en
`http://keycloak:8080/...`, tandis que le navigateur reçoit toujours des
endpoints frontchannel (authorization, logout) en `http://localhost:8080/...`.
L'`issuer` reste identique dans les deux cas — la validation JWT (issuer,
audience, signature) fonctionne donc sans aucun contournement, et sans
avoir à modifier le fichier hosts de la machine. Vérifié en pratique :
`curl http://localhost:8080/realms/enervision/.well-known/openid-configuration`
et le même appel depuis un conteneur du réseau `enervision_network`
renvoient le même `issuer` mais des `token_endpoint`/`jwks_uri`
différents, chacun correct pour son contexte.

Réseau Docker : `enervision_network` reste `external: true` en base (comme
en prod, où il est partagé avec l'infra existante), mais
`docker-compose.local.yml` le redéfinit en réseau géré par Compose — un
clone neuf n'a donc **pas** besoin de `docker network create`.

`frontend/.streamlit/secrets.toml` (copié depuis `.example`, non commité)
doit pointer vers ce Keycloak local :

```toml
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "<générer avec python -c \"import secrets; print(secrets.token_hex(32))\">"
client_id = "enervision-frontend"
client_secret = "local-dev-frontend-secret"
server_metadata_url = "http://keycloak:8080/realms/enervision/.well-known/openid-configuration"
expose_tokens = ["access"]
```

### Traefik local

Reproduit le routage HTTPS de prod en local (`traefik/dynamic.yml`,
routage minimal `localhost` → `frontend`/`backend`, à adapter si besoin).
Certificat local auto-signé à générer une fois (gitignoré, jamais
commité) :

```powershell
# Nécessite openssl (Git for Windows / WSL)
openssl req -x509 -newkey rsa:2048 -nodes -days 825 `
  -keyout certs/key.pem -out certs/cert.pem `
  -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost"
```

Puis `https://localhost/` (frontend) et `https://localhost/health` (backend).

## Configuration Keycloak — staging / production (actions manuelles)

Keycloak est déjà déployé sur l'infrastructure — il n'est pas ajouté à ce
repo, et ce qui suit ne concerne que staging/production (le local est
entièrement automatisé, voir section précédente). Dans la console
d'administration :

**Realm** : `enervision` (existant, déjà utilisé par `enervision-api`).

**Nouveau client à créer : `enervision-frontend`**

| Paramètre | Valeur |
|---|---|
| Client type | OpenID Connect |
| Client authentication | ON (confidentiel) |
| Standard flow | ON |
| Implicit flow | OFF |
| Direct access grants | OFF |
| Valid redirect URIs | `http://localhost:8501/oauth2callback` (dev), + l'URL publique du frontend en prod une fois son routeur Traefik créé |
| Web origins | `http://localhost:8501` (dev), + origine publique en prod |

Le **Client secret** se récupère dans l'onglet *Credentials* du client,
une fois créé. À reporter dans `frontend/.streamlit/secrets.toml`
(`client_secret`), jamais dans le code ni dans Git.

**Mapper d'audience requis** (pour que `backend/core` valide l'`aud`) :
sur le client `enervision-frontend` (ou un client scope qui lui est
assigné), ajouter un mapper *Audience* :
- Included Client Audience : `enervision-api`

Sans ce mapper, les tokens émis pour le frontend n'auront pas
`enervision-api` dans leur claim `aud`, et `backend/core` les rejettera.

## Lancer en local

```powershell
Copy-Item .env.local.example .env.local
Copy-Item frontend\.streamlit\secrets.toml.example frontend\.streamlit\secrets.toml
# éditer frontend\.streamlit\secrets.toml : client_secret = "local-dev-frontend-secret", cookie_secret = <générer>
openssl req -x509 -newkey rsa:2048 -nodes -days 825 -keyout certs\key.pem -out certs\cert.pem -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost"

.\docker.ps1 local up -d
```

- Frontend : `https://localhost/` (Traefik) ou `http://localhost:8501` (direct)
- Keycloak : `http://localhost:8080` (admin `admin`/`admin`)
- Backend (`core`) : `https://localhost/api/...` (Traefik) ou `http://localhost:8000/docs` (direct)
- Health : `https://localhost/health` (Traefik) ou `http://localhost:8002/health` (direct)

## Arrêter le local

```powershell
.\docker.ps1 local down
```

## Repartir de zéro (local)

Efface aussi les volumes (données PostgreSQL, état interne Keycloak) — le
realm `enervision` est ensuite ré-importé automatiquement au prochain
démarrage depuis `keycloak/realm-export.json` :

```powershell
.\docker.ps1 local down -v
.\docker.ps1 local up -d
```

## Production

```bash
docker compose up -d
```

utilise `docker-compose.yaml` seul (configuration commune, base de
production) avec le fichier `.env` (copié depuis
`.env.production.example`) : **pas** de Keycloak local, **pas** de
Traefik local, pas de bind mount ni de `--reload`. L'application se
connecte au Keycloak déjà déployé sur l'infrastructure via `KEYCLOAK_URL`.
Équivalent explicite : `.\docker.ps1 prod up -d`.

## Tester le flux d'authentification

Avec le Keycloak local, se connecter avec `test` / `test`.

1. Ouvrir `http://localhost:8501` → écran "Se connecter" (dashboard
   inaccessible tant que non authentifié).
2. Cliquer "Se connecter" → redirection vers Keycloak → saisir
   identifiant/mot de passe **sur Keycloak**.
3. Retour automatique sur le frontend, dashboard accessible, nom
   d'utilisateur affiché dans la sidebar.
4. La sidebar affiche aussi le statut de l'appel `GET /api/v1/me` vers
   `backend/core`, qui prouve que le token est transmis et validé côté
   API.
5. "Déconnexion" → retour à l'écran de connexion.

Pour tester `backend/core` isolément :

```bash
curl http://localhost:8000/api/v1/me
# -> 401 sans token

curl -H "Authorization: Bearer <access_token>" http://localhost:8000/api/v1/me
# -> 200 avec l'identité extraite du token
```

## Tests

```bash
# Backend
PYTHONPATH=backend pytest backend

# Frontend
PYTHONPATH=frontend pytest frontend/tests
```
