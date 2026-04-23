# Garmin Scraper Markdown Export Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Construire une application web qui extrait des activites de course Garmin Connect, les normalise et produit un Markdown structure, compact et exploitable par un LLM.

**Architecture:** L'application est decouplee en deux services: un backend FastAPI responsable de l'authentification Garmin, de l'extraction, de la normalisation et du rendu Markdown; un frontend React/Next.js responsable de la saisie utilisateur, du lancement d'exports et de l'affichage du resultat. Les donnees sensibles ne sont jamais persistees en clair, et la logique Garmin est isolee derriere un adaptateur testable.

**Tech Stack:** Python, FastAPI, garminconnect, pandas, fitparse, jinja2, pytest, TypeScript, React ou Next.js, fetch REST, Markdown, YAML frontmatter.

## 1. Rappel D'Architecture

### Objectif fonctionnel

L'application doit permettre a un utilisateur de:

1. Saisir ses identifiants Garmin Connect depuis une interface web locale.
2. Demander l'export d'une activite precise ou d'une plage d'activites recentes.
3. Laisser le backend recuperer les donnees Garmin.
4. Transformer les donnees brutes en resume structure.
5. Recevoir un Markdown contenant des sections lisibles par un LLM.
6. Copier ou telecharger ce Markdown.

Le produit n'est pas un dashboard sportif complet. La priorite est la generation d'un contexte clair, stable et compact pour analyse IA.

### Approche recommandee

L'approche recommandee est un monorepo avec:

- `backend/`: API FastAPI, client Garmin, pipeline de normalisation, moteur Markdown.
- `frontend/`: interface React/Next.js, appels REST et affichage du Markdown.
- `docs/`: decisions d'architecture, exemples de Markdown et notes d'exploitation.

Cette approche est plus robuste qu'un script Python isole, car elle separe l'experience utilisateur du moteur de scraping. Elle reste plus simple qu'une architecture distribuee avec workers, base de donnees et file de messages, qui serait prematuree pour un usage personnel.

### Alternatives ecartees

1. **CLI Python uniquement**
   - Avantage: rapide a coder.
   - Limite: moins confortable pour gerer le 2FA, le choix d'activites et la copie du Markdown.

2. **Frontend qui appelle directement Garmin**
   - Avantage: moins de backend.
   - Limite: expose davantage les contraintes CORS, les secrets, les cookies et les details Garmin au navigateur.

3. **Backend complet avec base de donnees des le depart**
   - Avantage: historique local et meilleure observabilite.
   - Limite: complexite inutile pour le MVP. Un cache fichier court terme suffit au debut.

## 2. Flux De Donnees

### Flux nominal: export d'une activite

1. Le frontend affiche un formulaire d'identifiants Garmin et un selecteur d'export.
2. L'utilisateur choisit:
   - activite recente,
   - activite par ID,
   - ou plage de dates.
3. Le frontend appelle le backend via `POST /api/exports/markdown`.
4. Le backend valide la requete avec Pydantic.
5. Le backend initialise un client Garmin via `garminconnect`.
6. Le backend recupere le resume d'activite, les splits, les donnees physiologiques disponibles et eventuellement le fichier brut.
7. La couche de normalisation convertit les objets Garmin en modeles internes stables.
8. La couche d'agregation reduit la granularite:
   - pas de point par seconde dans le Markdown par defaut,
   - splits au kilometre,
   - moyennes, min, max et zones utiles,
   - signaux de recuperation si disponibles.
9. Le moteur Jinja2 rend le template Markdown.
10. FastAPI renvoie:

```json
{
  "status": "success",
  "markdown": "---\\nactivity_id: ...\\n---\\n..."
}
```

### Flux 2FA

Garmin peut interrompre l'authentification avec une demande de code. Le backend doit donc supporter un flux en deux temps:

1. `POST /api/auth/start`
   - Entree: email, mot de passe.
   - Sortie possible: `authenticated` ou `mfa_required`.
2. `POST /api/auth/complete`
   - Entree: `auth_session_id`, code 2FA.
   - Sortie: session authentifiee courte duree.
3. `POST /api/exports/markdown`
   - Entree: `auth_session_id` ou credentials pour le mode MVP.

Pour le MVP, il est acceptable de commencer avec un endpoint unique incluant un champ optionnel `mfa_code`, mais la structure cible doit prevoir la separation du demarrage et de la finalisation du login.

### Flux multi-activites

Pour l'analyse long terme:

1. Le frontend envoie une plage de dates ou un nombre d'activites.
2. Le backend recupere la liste des activites.
3. Chaque activite est normalisee independamment.
4. Un document Markdown global est rendu avec:
   - frontmatter de periode,
   - resume global,
   - sections par activite,
   - tableaux comparatifs.

Ce flux doit limiter le volume pour respecter les fenetres de contexte LLM.

## 3. Contrats API

### `GET /api/health`

Verifie que le backend est disponible.

Reponse:

```json
{
  "status": "ok",
  "service": "garmin-scraper-api"
}
```

### `POST /api/auth/start`

Demarre une authentification Garmin.

Requete:

```json
{
  "email": "user@example.com",
  "password": "secret"
}
```

Reponses:

```json
{
  "status": "authenticated",
  "auth_session_id": "short-lived-session-id"
}
```

```json
{
  "status": "mfa_required",
  "auth_session_id": "short-lived-session-id",
  "message": "Garmin requires a verification code."
}
```

### `POST /api/auth/complete`

Finalise une authentification 2FA.

Requete:

```json
{
  "auth_session_id": "short-lived-session-id",
  "mfa_code": "123456"
}
```

Reponse:

```json
{
  "status": "authenticated",
  "auth_session_id": "short-lived-session-id"
}
```

### `POST /api/exports/markdown`

Genere un Markdown depuis Garmin.

Requete MVP:

```json
{
  "email": "user@example.com",
  "password": "secret",
  "activity_id": "123456789",
  "include_notes": true
}
```

Requete cible:

```json
{
  "auth_session_id": "short-lived-session-id",
  "mode": "single_activity",
  "activity_id": "123456789",
  "notes": "#chaleur #chaussures"
}
```

Reponse:

```json
{
  "status": "success",
  "markdown": "---\\nactivity_id: 123456789\\n---\\n...",
  "metadata": {
    "activity_count": 1,
    "generated_at": "2026-04-19T12:00:00Z"
  }
}
```

### `POST /api/exports/batch-markdown`

Genere un Markdown multi-activites.

Requete:

```json
{
  "auth_session_id": "short-lived-session-id",
  "date_from": "2026-01-01",
  "date_to": "2026-04-19",
  "activity_type": "running",
  "max_activities": 30
}
```

## 4. Modele De Donnees Interne

Les modeles internes doivent etre independants des noms de champs Garmin, qui peuvent changer.

### `ActivitySummary`

Champs cibles:

- `activity_id`
- `date`
- `activity_type`
- `title`
- `distance_km`
- `duration_seconds`
- `moving_duration_seconds`
- `average_pace_min_per_km`
- `average_hr`
- `max_hr`
- `training_load`
- `training_effect_aerobic`
- `training_effect_anaerobic`
- `elevation_gain_m`
- `calories`
- `vo2max`
- `perceived_effort`
- `weather`

### `PhysiologySnapshot`

Champs cibles:

- `resting_hr`
- `hrv_status`
- `hrv_avg_ms`
- `body_battery_start`
- `body_battery_end`
- `stress_avg`
- `sleep_score`
- `recovery_time_hours`
- `training_readiness`

Tous ces champs doivent etre optionnels: Garmin ne les expose pas toujours selon la montre, le pays, l'activite et les permissions.

### `Split`

Champs cibles:

- `index`
- `distance_km`
- `duration_seconds`
- `pace_min_per_km`
- `average_hr`
- `max_hr`
- `elevation_gain_m`
- `elevation_loss_m`
- `cadence_spm`
- `stride_length_m`

## 5. Markdown Cible

### Exemple de sortie

```markdown
---
activity_id: "123456789"
date: "2026-04-19"
activity_type: "running"
title: "Endurance fondamentale"
training_load: 142
fitness_state: "productive"
source: "Garmin Connect"
schema_version: "1.0"
---

# Seance Garmin - 2026-04-19

## Resume

- Distance: 10.24 km
- Duree: 00:52:13
- Allure moyenne: 5:06 /km
- Frequence cardiaque moyenne: 148 bpm
- Denivele positif: 86 m
- Charge d'entrainement: 142

## Performance

| Metrique | Valeur |
| --- | ---: |
| Distance | 10.24 km |
| Allure moyenne | 5:06 /km |
| FC moyenne | 148 bpm |
| FC max | 174 bpm |
| Training Effect aerobie | 3.2 |
| Training Effect anaerobie | 0.8 |

## Physiologie Et Recuperation

| Metrique | Valeur |
| --- | ---: |
| HRV moyenne | 54 ms |
| Body Battery debut | 72 |
| Body Battery fin | 41 |
| Stress moyen | 28 |
| Temps de recuperation | 18 h |

## Splits Par Km

| Km | Temps | Allure | FC moy | FC max | D+ |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 05:18 | 5:18/km | 137 | 149 | 8 m |
| 2 | 05:08 | 5:08/km | 144 | 153 | 4 m |

## Notes Contextuelles

#chaleur #chaussures
```

### Regles de generation

- Le frontmatter YAML doit rester stable pour faciliter l'indexation.
- Les valeurs absentes doivent etre rendues comme `null` en frontmatter et `Non disponible` dans les sections lisibles.
- Les donnees point-par-point ne doivent pas etre incluses par defaut.
- Les splits doivent etre arrondis de maniere coherente.
- Le Markdown doit etre valide meme si certaines metriques Garmin manquent.
- Un champ `schema_version` doit etre inclus pour permettre des evolutions futures.

## 6. Arborescence Cible

```text
garmin_scrapper/
  backend/
    app/
      __init__.py
      main.py
      api/
        __init__.py
        routes_auth.py
        routes_exports.py
        routes_health.py
      core/
        __init__.py
        config.py
        cors.py
        errors.py
        security.py
      garmin/
        __init__.py
        client.py
        cache.py
        exceptions.py
      processing/
        __init__.py
        aggregator.py
        mapper.py
        metrics.py
      markdown/
        __init__.py
        renderer.py
        templates/
          activity.md.j2
          batch.md.j2
      schemas/
        __init__.py
        auth.py
        exports.py
        internal.py
      tests/
        conftest.py
        test_health.py
        test_markdown_renderer.py
        test_mapper.py
        test_exports_api.py
    pyproject.toml
    .env.example
    README.md
  frontend/
    src/
      app/
        page.tsx
        layout.tsx
      components/
        CredentialsForm.tsx
        ExportOptions.tsx
        MarkdownPreview.tsx
      lib/
        api.ts
        types.ts
    package.json
    tsconfig.json
    .env.local.example
    README.md
  docs/
    adr/
      0001-decoupled-fastapi-react.md
    examples/
      single-activity.md
      batch-activities.md
    plans/
      2026-04-19-garmin-scraper-dat-plan.md
  .gitignore
  README.md
```

## 7. Installation Et Commandes

### Initialisation backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install fastapi uvicorn garminconnect pandas fitparse jinja2 pydantic pydantic-settings python-dotenv
pip install --group dev pytest pytest-cov httpx ruff mypy
```

Si `pip install --group dev` n'est pas supporte par la configuration choisie, utiliser des dependances `dev` dans `pyproject.toml` puis installer avec:

```bash
pip install -e ".[dev]"
```

### Lancement backend

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Initialisation frontend

Option Next.js recommandee:

```bash
npx create-next-app@latest frontend --ts --eslint --app --src-dir
cd frontend
npm install
```

Variables frontend:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

### Lancement frontend

```bash
cd frontend
npm run dev
```

### Verification

```bash
cd backend
pytest
ruff check .
mypy app
```

```bash
cd frontend
npm run lint
npm run build
```

## 8. Configuration

### Backend `.env`

```env
APP_ENV=local
API_HOST=127.0.0.1
API_PORT=8000
FRONTEND_ORIGIN=http://localhost:3000
GARMIN_CACHE_TTL_SECONDS=900
GARMIN_MIN_REQUEST_INTERVAL_SECONDS=2
AUTH_SESSION_TTL_SECONDS=600
```

### Frontend `.env.local`

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## 9. Points De Vigilance

### CORS

FastAPI doit autoriser uniquement les origines attendues:

- `http://localhost:3000`
- eventuellement `http://127.0.0.1:3000`

Ne pas utiliser `allow_origins=["*"]` avec des endpoints manipulant des identifiants.

### Securite des identifiants

- Ne jamais logger `email`, `password`, token, cookie ou code 2FA.
- Ne jamais stocker le mot de passe Garmin.
- Garder les sessions Garmin en memoire ou dans un cache chiffre et court terme.
- Ajouter un middleware de redaction des logs si des exceptions remontent les payloads.
- Prevoir HTTPS si l'application sort du strict usage local.

### 2FA Garmin

La bibliotheque `garminconnect` s'appuie sur une API non officielle. Le comportement exact du 2FA doit etre valide pendant l'implementation contre la version installee de la lib. La couche `garmin/client.py` doit masquer ces details au reste de l'application.

### Rate limiting Garmin

- Imposer un delai minimal entre les appels.
- Mettre en cache les activites deja recuperees.
- Limiter les exports batch avec `max_activities`.
- Eviter les retries agressifs.
- Ajouter des erreurs explicites quand Garmin refuse ou limite les appels.

### Robustesse des donnees

- Toute metrique Garmin doit etre consideree optionnelle.
- Les mappings doivent etre testes avec des fixtures JSON.
- Les changements de schema Garmin ne doivent pas casser le rendu Markdown.

### Donnees LLM

- Ne pas inclure les traces GPS detaillees par defaut.
- Ne pas inclure tous les points de frequence cardiaque.
- Preferer les agragats, splits et tendances.
- Prevoir un mode `verbose` plus tard, mais le MVP doit rester compact.

## 10. Plan De Developpement Step-By-Step

### Phase 0: Socle projet

**Files:**
- Create: `README.md`
- Create: `.gitignore`
- Create: `backend/pyproject.toml`
- Create: `backend/.env.example`
- Create: `frontend/.env.local.example`
- Create: `docs/adr/0001-decoupled-fastapi-react.md`

**Step 1: Initialiser le depot**

```bash
git init
```

Expected: un depot Git local est cree.

**Step 2: Creer les dossiers racines**

```bash
mkdir -p backend/app frontend docs/adr docs/examples docs/plans
```

Expected: l'arborescence de base existe.

**Step 3: Ajouter `.gitignore`**

Inclure au minimum:

```gitignore
.env
.env.local
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
.mypy_cache/
node_modules/
.next/
dist/
build/
*.log
```

**Step 4: Commit**

```bash
git add .
git commit -m "chore: initialize project structure"
```

### Phase 1: Backend FastAPI minimal

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/api/routes_health.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/cors.py`
- Test: `backend/tests/test_health.py`

**Step 1: Ecrire le test healthcheck**

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok():
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

**Step 2: Lancer le test pour verifier l'echec**

```bash
cd backend
pytest tests/test_health.py -v
```

Expected: FAIL car `app.main` ou la route n'existe pas encore.

**Step 3: Implementer FastAPI minimal**

Creer `app/api/routes_health.py`:

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "garmin-scraper-api"}
```

Creer `app/main.py`:

```python
from fastapi import FastAPI

from app.api.routes_health import router as health_router

app = FastAPI(title="Garmin Scraper API")
app.include_router(health_router)
```

**Step 4: Verifier**

```bash
pytest tests/test_health.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend
git commit -m "feat: add FastAPI health endpoint"
```

### Phase 2: Schemas et modeles internes

**Files:**
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/schemas/exports.py`
- Create: `backend/app/schemas/internal.py`
- Test: `backend/tests/test_schemas.py`

**Step 1: Definir les modeles Pydantic**

Creer des modeles pour:

- `AuthStartRequest`
- `AuthCompleteRequest`
- `MarkdownExportRequest`
- `MarkdownExportResponse`
- `ActivitySummary`
- `PhysiologySnapshot`
- `Split`
- `NormalizedActivity`

**Step 2: Tester les valeurs optionnelles**

Verifier qu'une activite sans HRV, Body Battery ou Training Load reste valide.

**Step 3: Commit**

```bash
git add backend/app/schemas backend/tests/test_schemas.py
git commit -m "feat: add API and activity schemas"
```

### Phase 3: Rendu Markdown

**Files:**
- Create: `backend/app/markdown/renderer.py`
- Create: `backend/app/markdown/templates/activity.md.j2`
- Create: `backend/app/markdown/templates/batch.md.j2`
- Test: `backend/tests/test_markdown_renderer.py`

**Step 1: Ecrire une fixture d'activite normalisee**

Utiliser un objet `NormalizedActivity` sans dependance Garmin.

**Step 2: Tester le rendu**

Assertions minimales:

- le Markdown commence par `---`,
- contient `activity_id`,
- contient `## Performance`,
- contient `## Physiologie Et Recuperation`,
- contient `## Splits Par Km`,
- rend un tableau Markdown de splits.

**Step 3: Implementer `MarkdownRenderer`**

Le renderer charge les templates Jinja2 depuis `templates/` et expose:

- `render_activity(activity: NormalizedActivity, notes: str | None) -> str`
- `render_batch(activities: list[NormalizedActivity], notes: str | None) -> str`

**Step 4: Commit**

```bash
git add backend/app/markdown backend/tests/test_markdown_renderer.py
git commit -m "feat: render normalized activities as markdown"
```

### Phase 4: Mapping Garmin vers modele interne

**Files:**
- Create: `backend/app/processing/mapper.py`
- Create: `backend/app/processing/metrics.py`
- Create: `backend/tests/fixtures/garmin_activity_summary.json`
- Create: `backend/tests/fixtures/garmin_activity_splits.json`
- Test: `backend/tests/test_mapper.py`

**Step 1: Ajouter des fixtures anonymisees**

Les fixtures ne doivent contenir aucune donnee personnelle sensible. Si elles viennent d'un vrai export Garmin, retirer:

- nom,
- coordonnees GPS precises,
- lieux,
- device identifiers,
- tokens,
- emails.

**Step 2: Tester le mapping**

Verifier:

- distance metres vers kilometres,
- secondes vers allure min/km,
- splits Garmin vers `Split`,
- champs absents vers `None`.

**Step 3: Implementer le mapper**

`mapper.py` doit convertir les dictionnaires Garmin en `NormalizedActivity` sans appeler Garmin.

**Step 4: Commit**

```bash
git add backend/app/processing backend/tests
git commit -m "feat: map Garmin payloads to normalized activities"
```

### Phase 5: Client Garmin et cache

**Files:**
- Create: `backend/app/garmin/client.py`
- Create: `backend/app/garmin/cache.py`
- Create: `backend/app/garmin/exceptions.py`
- Test: `backend/tests/test_garmin_cache.py`

**Step 1: Creer l'interface client**

`GarminClient` doit exposer:

- `login(email: str, password: str) -> GarminSession`
- `complete_mfa(session_id: str, code: str) -> GarminSession`
- `get_activity(activity_id: str) -> dict`
- `get_activity_splits(activity_id: str) -> list[dict]`
- `list_running_activities(date_from, date_to, limit) -> list[dict]`

**Step 2: Ajouter un cache TTL**

Le cache peut etre fichier ou memoire pour le MVP. Il doit eviter de rappeler Garmin pour la meme activite pendant une courte periode.

**Step 3: Ajouter un rate limiter simple**

Avant chaque appel Garmin, respecter `GARMIN_MIN_REQUEST_INTERVAL_SECONDS`.

**Step 4: Tester le cache sans appeler Garmin**

Mocker le client bas niveau et verifier que le deuxieme appel utilise le cache.

**Step 5: Commit**

```bash
git add backend/app/garmin backend/tests/test_garmin_cache.py
git commit -m "feat: add Garmin client wrapper and cache"
```

### Phase 6: Endpoints d'export

**Files:**
- Create: `backend/app/api/routes_exports.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_exports_api.py`

**Step 1: Tester l'endpoint avec dependances mockees**

Le test ne doit jamais appeler Garmin. Il mocke:

- client Garmin,
- mapper,
- renderer.

**Step 2: Implementer `POST /api/exports/markdown`**

Pipeline:

1. valider la requete,
2. authentifier ou recuperer la session,
3. recuperer les payloads Garmin,
4. mapper vers modele interne,
5. rendre le Markdown,
6. renvoyer JSON.

**Step 3: Implementer erreurs propres**

Mapper:

- erreur credentials vers HTTP 401,
- rate limit vers HTTP 429,
- activite introuvable vers HTTP 404,
- erreur Garmin inconnue vers HTTP 502.

**Step 4: Commit**

```bash
git add backend/app/api backend/app/main.py backend/tests/test_exports_api.py
git commit -m "feat: expose markdown export endpoint"
```

### Phase 7: CORS et configuration

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/core/cors.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_cors.py`

**Step 1: Tester l'origine frontend**

Verifier qu'une requete preflight depuis `http://localhost:3000` est acceptee.

**Step 2: Implementer `CORSMiddleware`**

Utiliser la variable `FRONTEND_ORIGIN`.

**Step 3: Commit**

```bash
git add backend/app/core backend/app/main.py backend/tests/test_cors.py
git commit -m "feat: configure CORS for frontend origin"
```

### Phase 8: Frontend MVP

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/src/components/CredentialsForm.tsx`
- Create: `frontend/src/components/ExportOptions.tsx`
- Create: `frontend/src/components/MarkdownPreview.tsx`
- Modify: `frontend/src/app/page.tsx`

**Step 1: Creer les types TypeScript**

Types:

- `MarkdownExportRequest`
- `MarkdownExportResponse`
- `ApiError`

**Step 2: Creer le client API**

`exportMarkdown(payload)` appelle `POST /api/exports/markdown`.

**Step 3: Creer le formulaire**

Champs:

- email,
- mot de passe,
- activity ID,
- notes contextuelles.

**Step 4: Afficher le Markdown**

Le composant `MarkdownPreview` doit permettre:

- lecture,
- copie presse-papiers,
- telechargement `.md`.

**Step 5: Verifier**

```bash
cd frontend
npm run lint
npm run build
```

**Step 6: Commit**

```bash
git add frontend
git commit -m "feat: add frontend markdown export flow"
```

### Phase 9: Export batch

**Files:**
- Modify: `backend/app/api/routes_exports.py`
- Modify: `backend/app/markdown/templates/batch.md.j2`
- Modify: `frontend/src/components/ExportOptions.tsx`
- Test: `backend/tests/test_batch_export.py`

**Step 1: Tester l'export multi-activites**

Verifier que le Markdown contient:

- frontmatter de periode,
- nombre d'activites,
- resume global,
- sections par activite.

**Step 2: Implementer le backend batch**

Limiter `max_activities` pour eviter l'abus de Garmin et les documents trop longs.

**Step 3: Ajouter l'option frontend**

Mode:

- single activity,
- date range.

**Step 4: Commit**

```bash
git add backend frontend
git commit -m "feat: add batch markdown exports"
```

### Phase 10: Documentation et durcissement

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `frontend/README.md`
- Create: `docs/examples/single-activity.md`
- Create: `docs/examples/batch-activities.md`

**Step 1: Documenter le lancement local**

Inclure:

- installation backend,
- installation frontend,
- variables d'environnement,
- limites Garmin,
- comportement 2FA.

**Step 2: Ajouter exemples Markdown**

Fournir des exemples anonymises.

**Step 3: Verification complete**

```bash
cd backend
pytest
ruff check .
mypy app
```

```bash
cd frontend
npm run lint
npm run build
```

**Step 4: Commit**

```bash
git add README.md backend/README.md frontend/README.md docs
git commit -m "docs: document local setup and markdown format"
```

## 11. Definition Of Done MVP

Le MVP est termine lorsque:

- le backend demarre localement sur `127.0.0.1:8000`,
- `GET /api/health` repond correctement,
- le frontend demarre localement sur `localhost:3000`,
- un export d'activite unique retourne un Markdown valide,
- le Markdown contient frontmatter, performance, physiologie, splits et notes,
- les mots de passe ne sont ni stockes ni logges,
- les tests backend du mapping et du renderer passent,
- le CORS est configure pour le frontend local,
- les erreurs Garmin principales sont converties en erreurs HTTP comprehensibles.

## 12. Roadmap Apres MVP

1. Ajouter un vrai gestionnaire de session chiffre si l'app devient multi-utilisateur.
2. Ajouter un stockage local optionnel des exports Markdown.
3. Ajouter une page d'historique d'exports.
4. Ajouter un mode comparaison entre periodes.
5. Ajouter un export ZIP contenant plusieurs fichiers Markdown.
6. Ajouter un mode de redaction automatique des donnees sensibles.
7. Ajouter des tests d'integration optionnels derriere une variable `RUN_GARMIN_INTEGRATION_TESTS=1`.
