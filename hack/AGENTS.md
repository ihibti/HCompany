# Tomate — extension Chrome qui jette des tomates sur les vidéos hors sujet

## Setup
- `.env` à la racine (HAI_API_KEY, LINKUP_API_KEY, GLADIA_API_KEY) — jamais commité, chargé par backend/app/config.py (env_file="../.env").
- `cd backend && uv sync`
- `cd extension && npm install && npm run build` (prod) ou `npm run build:dev` (ajoute http://localhost:8899/* aux matches pour les fixtures).
- Charger `extension/dist/` dans chrome://extensions (mode développeur).

## Run
- `./dev.sh` — fixtures :8899 + backend RÉEL :8787 + backend FAKE_AI :8790 (démo/tests).
- Fixtures de démo : http://localhost:8899/{youtube,tiktok,instagram}.html — créer un profil dans le side panel, ou via `chrome.storage.local.set({profileId:"<id>"})`.

## Test
- `cd backend && uv run pytest` (aucun réseau ; Holo/Linkup/H injectés).
- `cd extension && npm run build` + `npm run lint`.
- E2E : `cd tests && node e2e.mjs` (nécessite backend FAKE_AI=1 :8787 + fixtures :8899 + extension build:dev).

## Backend (port 8787)
Endpoints : /health /profile /classify /feedback /train /scout /login /jobs.
H Agents : file asyncio, un worker (un seul profil navigateur à la fois), agent_view_url exposé dès le démarrage. /train /scout /login nécessitent le compte utilisateur connecté (navigateur cloud `use_default_browser_profile`) — ne pas lancer sans accord de l'utilisateur.
