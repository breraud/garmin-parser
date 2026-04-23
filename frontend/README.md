# Frontend Garmin Scraper

Application Next.js pour lancer les exports Garmin vers Markdown.

## Installation

```bash
npm install
cp .env.local.example .env.local
```

## Configuration

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:3567
```

## Lancement

```bash
npm run dev
```

Ouvrir `http://localhost:3568`.

## Utilisation

1. Renseigner email et mot de passe Garmin.
2. Choisir `Activite unique` ou `Plage de dates`.
3. Pour une activite unique, saisir l'ID Garmin.
4. Pour un batch, saisir la date de debut, la date de fin et `Nombre max d'activites`.
5. Ajouter des notes ou tags contextuels.
6. Generer le Markdown, puis copier ou telecharger le fichier `.md`.

## Erreurs Affichees

- `401`: identifiants invalides ou challenge Garmin non finalise.
- `404`: activite introuvable.
- `429`: limitation temporaire Garmin.
- `502`: Garmin ne repond pas correctement.

## Verification

```bash
npm run lint
npm run build
```
