# Garmin Scraper

Application web locale pour extraire des activites de course Garmin Connect et les transformer en Markdown structure, compact et exploitable par un LLM.

## Architecture

Le projet est decoupe en deux applications:

- `backend/`: API FastAPI, client Garmin, cache, mapping des donnees Garmin et rendu Markdown Jinja2.
- `frontend/`: application Next.js pour saisir les informations Garmin, lancer un export et copier ou telecharger le Markdown.

Flux principal:

1. Le frontend envoie une requete REST au backend.
2. Le backend s'authentifie aupres de Garmin Connect via `garminconnect`.
3. Le backend recupere une activite unique ou une plage d'activites.
4. Les payloads Garmin sont normalises en modeles internes Pydantic.
5. Jinja2 rend un Markdown avec frontmatter YAML, sections performance, physiologie et splits.
6. Le frontend affiche le Markdown pour copie ou telechargement.

## Prerequis

- Python 3.12 recommande.
- Node.js 25 ou version LTS recente.
- Un compte Garmin Connect.

## Installation

Backend:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
```

Frontend:

```bash
cd frontend
npm install
cp .env.local.example .env.local
```

## Lancement Local

Terminal 1:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 3567
```

Terminal 2:

```bash
cd frontend
npm run dev
```

Ouvrir ensuite `http://localhost:3568`.

## Configuration

Backend `.env`:

```env
APP_ENV=local
API_HOST=127.0.0.1
API_PORT=3567
FRONTEND_ORIGIN=http://localhost:3568
GARMIN_CACHE_TTL_SECONDS=900
GARMIN_MIN_REQUEST_INTERVAL_SECONDS=2
AUTH_SESSION_TTL_SECONDS=600
```

Frontend `.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:3567
```

## Exports Disponibles

- Activite unique: `POST /api/exports/markdown`
- Plage de dates: `POST /api/exports/batch-markdown`

Le batch respecte `max_activities` pour limiter les appels Garmin et produire un Markdown compatible avec une fenetre de contexte LLM.

## 2FA Garmin

La librairie `garminconnect` peut demander un code MFA selon l'etat du compte Garmin. Le backend contient deja les primitives d'erreur et de session pour gerer ce flux. La V1 utilise le mode credentials direct depuis le formulaire; si Garmin demande un code 2FA, l'appel renverra une erreur d'authentification explicite plutot que de stocker le mot de passe.

## Securite

- Les mots de passe Garmin ne sont pas stockes.
- Les tests mockent les appels Garmin et ne declenchent pas de requetes reseau.
- Le cache backend limite les appels repetes pour une meme activite.
- CORS est limite a `FRONTEND_ORIGIN`.

## Verification

Backend:

```bash
cd backend
source .venv/bin/activate
pytest
ruff check .
mypy app
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

## Exemples

- `docs/examples/single-activity.md`
- `docs/examples/batch-activities.md`
