#!/usr/bin/env bash
# Tomate demo: backend (:8787, FAKE_AI=1 pour la démo sans clés) + fixtures (:8899).
# Pour le vrai backend IA : (cd backend && uv run uvicorn app.main:app --port 8787)
set -e
cd "$(dirname "$0")"
(cd fixtures && python3 -m http.server 8899) &
(cd backend && uv run uvicorn app.main:app --port 8787 --reload) &
(cd backend && FAKE_AI=1 uv run uvicorn app.main:app --port 8790) &
wait
