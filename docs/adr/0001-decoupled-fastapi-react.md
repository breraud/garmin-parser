# ADR 0001: Architecture decouplee FastAPI et React

## Statut

Acceptee.

## Contexte

L'application doit extraire des donnees de course depuis Garmin Connect, les normaliser et produire un Markdown stable pour analyse par un LLM. Le scraping Garmin manipule des identifiants, des sessions et une API non officielle. L'interface utilisateur doit rester simple et ne pas exposer les details Garmin au navigateur.

## Decision

Le projet utilise une architecture decouplee:

- Backend Python FastAPI pour l'authentification Garmin, l'extraction, la transformation et le rendu Markdown.
- Frontend React/Next.js pour la saisie utilisateur, le lancement d'exports et l'affichage du Markdown.
- Communication REST en JSON entre frontend et backend.

## Consequences

Cette separation permet de tester le pipeline backend sans interface graphique et de faire evoluer le frontend sans modifier la logique Garmin. Elle ajoute un service local supplementaire a lancer, mais garde les responsabilites claires et limite l'exposition des identifiants Garmin au navigateur.

