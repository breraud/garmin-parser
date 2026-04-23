# Backend Garmin Scraper

API FastAPI responsable de l'authentification Garmin, de la recuperation des activites, du mapping vers des modeles Pydantic et du rendu Markdown.

## Installation

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
```

## Variables D'Environnement

```env
APP_ENV=local
API_HOST=127.0.0.1
API_PORT=3567
FRONTEND_ORIGIN=http://localhost:3568
GARMIN_CACHE_TTL_SECONDS=900
GARMIN_MIN_REQUEST_INTERVAL_SECONDS=2
AUTH_SESSION_TTL_SECONDS=600
```

`GARMIN_MIN_REQUEST_INTERVAL_SECONDS` evite d'enchainer les appels Garmin trop vite. `GARMIN_CACHE_TTL_SECONDS` garde temporairement les activites deja recuperees pour limiter les appels repetes.

## Lancement

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 3567
```

Healthcheck:

```bash
curl http://127.0.0.1:3567/api/health
```

## Endpoints

### `POST /api/exports/markdown`

Genere un Markdown pour une activite precise.

```json
{
  "email": "runner@example.com",
  "password": "secret",
  "mode": "single_activity",
  "activity_id": "123456789",
  "notes": "#chaleur #chaussures"
}
```

### `POST /api/exports/batch-markdown`

Genere un Markdown pour une plage de dates.

```json
{
  "email": "runner@example.com",
  "password": "secret",
  "mode": "date_range",
  "date_from": "2026-04-01",
  "date_to": "2026-04-30",
  "max_activities": 10,
  "notes": "#cycle-printemps"
}
```

## 2FA Garmin

Garmin peut demander un code MFA. Le client `GarminClient` expose `complete_mfa`, mais le flux UI V1 reste volontairement simple. Si Garmin interrompt le login pour MFA, l'API renvoie une erreur d'authentification claire; aucun mot de passe n'est persiste.

## Tests Et Qualite

```bash
pytest
ruff check .
mypy app
```

Les tests mockent Garmin Connect et utilisent des fixtures anonymisees.
