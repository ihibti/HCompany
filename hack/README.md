# Tomate

Extension Chrome (Manifest V3) qui nettoie les fils YouTube, TikTok et Instagram. Tu décris en une phrase ce que tu veux voir (« de l'escalade et de la cuisine japonaise, pas de drama ni de gaming »). Un petit fermier en pâte à modeler surveille ensuite ton fil : il lance une tomate sur chaque vidéo hors sujet, la masque et la remplace par une vidéo qui correspond à ton profil. Si tu le demandes, un agent H va aussi corriger l'algorithme de la plateforme directement sur ton compte.

## Comment ça marche

1. **Profil**. Dans le panneau latéral, l'utilisateur écrit ses envies en langage naturel. Le backend demande à Holo (modèle « smart ») de structurer la demande en sujets voulus, sujets refusés, mots-clés et langues. Il lance ensuite, pour chaque sujet, une recherche Linkup qui ajoute des mots-clés, des créateurs de référence et des sources. Le panneau affiche l'avancement (« Je lis tes envies… », puis « Je cherche sur le web (Linkup)… »), puis le profil avec ses sources cliquables.
2. **Classification**. Le content script repère les tuiles vidéo grâce à un adaptateur DOM par plateforme. Les tuiles visibles passent en priorité. Elles partent par lots de 8 vers `/classify`, avec au plus 3 requêtes en parallèle. Le backend renvoie pour chacune un verdict `on` / `off` / `unsure`, une confiance et une raison courte en français. Une tuile `unsure` dont la confiance est inférieure à 0,6 repart vers `/classify/refine`, qui ajoute du contexte web via Linkup. Au-dessus de ce seuil, la tuile reçoit un badge « ? » qui permet à l'utilisateur de la garder ou de la tomater.
3. **Tomate et remplacement**. Une tuile `off` est voilée immédiatement (flou). La mascotte vise la tuile et lance la tomate en parabole, puis la tache apparaît avec la raison. La tuile est ensuite masquée et une fine bande « Tomatée : … — Pardon ? » prend sa place. Environ 400 ms plus tard, une carte de remplacement « Proposé par Tomate » est insérée au même endroit. Si le lanceur automatique est désactivé, la tuile reste seulement voilée.
4. **Feed Tomate (YouTube)**. Sur la page d'accueil de YouTube, une étagère « Ton feed Tomate » apparaît au-dessus de la grille, avec un bouton « Actualiser ». Elle est remplie par des recherches YouTube faites depuis la page elle-même (`ytPool.ts`) : 2 mots-clés et 1 créateur par sujet du profil, qui tournent à chaque « Actualiser » pour ramener des vidéos nouvelles ; les résultats des requêtes sont mélangés en round-robin pour que tous les sujets apparaissent. Chaque résultat passe par le classifieur et seuls les verdicts `on` de confiance ≥ 0,7 sont gardés. L'étagère suit la navigation SPA de YouTube et respecte son thème sombre. L'option « Remplacer tout l'accueil YouTube » du panneau masque la grille YouTube et affiche le feed Tomate en grille, avec un bouton « Plus de vidéos ».
5. **Retour utilisateur**. Il y a trois façons de lancer une tomate à la main : cliquer sur la mascotte, appuyer sur `T` (mode visée, `Échap` pour sortir), ou faire clic droit sur un lien puis « Lancer une tomate ». « Pardon ? », sur la tache, la bande ou la carte de remplacement, restaure la tuile. Chaque geste est envoyé à `/feedback`, qui invalide le verdict en cache. Les 20 derniers retours servent d'exemples dans le prompt de classification suivant.
6. **Entraînement H**. Le bouton « Entraîner maintenant » crée un job H Agents. Un agent pilote alors un vrai navigateur connecté au compte de l'utilisateur : « Pas intéressé » sur les vidéos tomatées, quelques recherches et visionnages dans le sujet, 1 à 2 likes par sujet au maximum. « Chercher pour moi » (scout) parcourt le fil et rapporte des vidéos dans le sujet. Le panneau suit les jobs et affiche le lien « Regarder l'agent » (Agent View) pendant l'exécution.

## Architecture

```
Chrome (youtube.com / tiktok.com / instagram.com)
+------------------------------------------------------------------+
| content script : adapters DOM -> tuiles -> verdicts              |
|   overlay en shadow DOM : mascotte, tomates, voiles, bandes,     |
|   cartes de remplacement, étagère « Ton feed Tomate »            |
|   ytPool : fetch same-origin youtube.com/results (ytInitialData) |
|        | chrome.runtime.sendMessage                              |
| service worker : relais fetch vers le backend, badge, menu       |
| side panel React : profil, réglages, compteurs, jobs H           |
+-----------------------------+------------------------------------+
                              | HTTP JSON (localhost:8787 par défaut)
+-----------------------------v------------------------------------+
| backend FastAPI                                                  |
|  /profile  /classify  /classify/refine  /feedback  /replacements |
|  /train  /scout  /login  /jobs   (file asyncio, 1 worker H)      |
|  store JSON : backend/data/{profiles,feedback,cache,logins}.json |
+--------+--------------------+--------------------+---------------+
         |                    |                    |
   Holo (H Models)        Linkup              H Agents (hai-agents)
   holo4 fast / smart     recherche web       navigateur piloté
   API OpenAI-compatible  structurée          (Chrome local ou cloud)
```

## Technologies et leur rôle

### H Company — modèles Holo
- Le client `openai` pointe vers `https://api.hcompany.ai/v1/` (`backend/app/core/holo.py`). Tous les appels utilisent des sorties structurées (`response_format: json_schema` généré depuis des modèles pydantic) et `temperature=0`. On n'a donc jamais de JSON à réparer à la main.
- **Holo smart** (`holo4-27b`, variable `HOLO_SMART_MODEL`) construit le profil. C'est un appel unique par profil, où la qualité de compréhension du texte libre compte plus que la latence. Le raisonnement est laissé au réglage par défaut du modèle.
- **Holo fast** (`holo4-35b-a3b`, variable `HOLO_FAST_MODEL`) sert à la classification et au refine. Il est appelé sur chaque tuile du fil, donc le raisonnement est coupé (`reasoning_effort: "none"`). Les vidéos sont envoyées par paquets de 8, avec au plus 4 appels en parallèle. Le prompt contient le profil et les 20 derniers retours de l'utilisateur, qui servent d'exemples.

### H Agents (`hai-agents[browser]`)
- Ce SDK fait le travail qu'aucune API publique ne permet : signaler « Pas intéressé », rechercher, regarder et liker sur le compte de l'utilisateur. Les algorithmes de recommandation n'apprennent que de ces actions.
- `backend/app/core/h_jobs.py` : `/train`, `/scout` et `/login` ajoutent un `Job` dans une `asyncio.Queue`. Un **worker unique** traite les jobs un par un, car un même profil navigateur ne peut être piloté que par une session à la fois.
- Chaque job ouvre une session avec `AsyncClient().start_session(...)` et un `answer_schema` pydantic (`TrainActions`, `ScoutItems` ou `LoginReport`). Le `session_id` et l'`agent_view_url` sont enregistrés sur le job **dès le démarrage**. Le panneau interroge `/jobs` toutes les 3 s et affiche le lien pendant l'exécution.
- **Environnement navigateur**. Par défaut (`H_LOCAL=true`), l'agent pilote un Chrome local (`host: "user_device"`). Le bouton « Ouvrir le Chrome d'entraînement » appelle `/local/open-browser`, qui ouvre un Chrome dédié (`~/.hai/chrome-profile`) sur la page de connexion Google. Avec `H_LOCAL=false`, l'agent utilise un navigateur cloud avec `use_default_browser_profile: true`.
- **Garde-fous de l'instruction `/train`** :
  - L'agent vérifie d'abord qu'il est connecté. Sinon il s'arrête et le job passe en échec avec un message explicite.
  - Il n'utilise que « Pas intéressé », jamais « Ne pas recommander la chaîne ».
  - Il fait 1 à 2 recherches par sujet et regarde 30 à 60 s de 2 ou 3 résultats.
  - Il met au plus 1 à 2 likes par sujet.
  - Il lui est interdit de s'abonner, de commenter ou de partager.
- **Scout** : l'agent fait défiler le fil et rapporte jusqu'à N contenus dans le sujet, avec `{url, title_or_caption, creator, why}`. Ces résultats sont affichés dans le panneau et ajoutés au pool de remplacements.

### Linkup (`linkup-sdk`)
Linkup intervient à trois endroits :
- **Enrichissement du profil** (`profile.py`) : une recherche `structured` en profondeur `standard` par sujet. Elle ajoute des mots-clés (15 au maximum) et des créateurs de référence (8 au maximum). Les **sources** sont dédupliquées et affichées dans le panneau, ce qui rend le profil vérifiable.
- **Refine** (`classify.py`) : pour les tuiles incertaines, jusqu'à 8 recherches `searchResults` en profondeur `fast`, lancées en parallèle sur « titre + chaîne ». Les extraits obtenus servent de contexte web à un nouvel appel Holo fast.
- **Candidats de remplacement** (`replacements.py`) : des requêtes `site:tiktok.com …`, `site:instagram.com/reel …` ou `site:youtube.com …` pour chaque mot-clé. Les URL sont normalisées en identifiants par regex. Les métadonnées sont ensuite complétées par oEmbed, ce qui écarte au passage les vidéos supprimées ou privées sur YouTube et TikTok. Instagram n'a pas d'oEmbed public, ses candidats ne sont donc pas vérifiés. Pour finir, tout passe par le classifieur (`on`, confiance ≥ 0,7). Le pool de chaque plateforme est reconstruit en tâche de fond dès qu'il descend sous 6 éléments.

Sur YouTube, l'extension préfère la recherche same-origin, plus rapide et plus riche (miniatures, durées). Le backend `/replacements` sert de solution de repli et de source pour TikTok et Instagram.

### Gladia
`GLADIA_API_KEY` est lue par la configuration, et `/health` indique seulement si elle est présente. Aucun appel à Gladia n'existe dans le code actuel.

### Backend : FastAPI, uv, pydantic
- **FastAPI** porte l'API JSON. Son CORS accepte `chrome-extension://*` et `localhost`, et un événement de démarrage lance le worker H.
- **uv** gère l'environnement Python 3.12 et le verrouillage des dépendances (`uv.lock`).
- **pydantic** décrit tous les schémas (`models.py`). Les mêmes modèles servent de JSON Schema pour Holo et H Agents.
- **pydantic-settings** charge `../.env` (`config.py`).
- **Stockage** (`store.py`) : de simples fichiers JSON dans `backend/data/`, un dossier ignoré par git.
  - `profiles.json` contient les profils.
  - `feedback.json` garde les 500 derniers retours.
  - `cache.json` stocke les verdicts, avec la clé `profil|plateforme|id`. Le cache vit en mémoire et est écrit sur disque au plus tard 2 s après une modification. Au-delà de 5000 entrées, il est réduit aux 3000 plus récentes.
  - `logins.json` enregistre l'état de connexion par plateforme.
  - Les jobs H et les pools de remplacements ne vivent qu'en mémoire.
- **Mode `FAKE_AI=1`** : un mode déterministe qui n'utilise pas le réseau.
  - Le profil est construit en découpant le texte.
  - La classification se fait par listes de mots-clés (escalade, ramen… = `on` ; drama, gaming… = `off`).
  - Les remplacements et les jobs H sont simulés.
  - Le panneau affiche un bandeau rouge « MODE SIMULÉ » et désactive les boutons H.
  - Ce mode sert à la démo sans clés et aux tests E2E.

### Extension : Chrome MV3, Vite, @crxjs/vite-plugin, TypeScript, React 19
- **Manifest V3** (`src/manifest.ts`, écrit en TypeScript avec `defineManifest`).
  - Permissions : `storage`, `sidePanel`, `activeTab`, `scripting`, `contextMenus`.
  - Content script injecté sur YouTube, TikTok et Instagram.
  - `npm run build:dev` (`CRX_FIXTURES=1`) ajoute `http://localhost:8899/*` pour les fixtures.
- **Vite + @crxjs/vite-plugin** compilent le manifest, le service worker, le content script et le panneau dans `extension/dist/`, sans configuration de bundling manuelle.
- **Service worker** (`src/sw.ts`) :
  - Il relaie les appels du content script vers le backend, ce qui évite le CORS et la CSP des pages.
  - Il gère le badge de l'icône (tomates actives).
  - Il crée le menu contextuel « Lancer une tomate » et ouvre le panneau latéral.
- **Side panel React 19** (`src/panel/main.tsx`) :
  - saisie du profil et affichage des sujets, créateurs et sources ;
  - réglages (plateformes, lanceur automatique, « Remplacer tout l'accueil ») ;
  - compteurs ;
  - actions H autorisées et suivi des jobs ;
  - URL du backend configurable (`backendUrl` dans `chrome.storage`).
- **Overlays en shadow DOM**. La mascotte, les tomates, les taches, les voiles, les badges « ? », les bandes, les cartes de remplacement et l'étagère vivent dans des shadow roots (`:host { all: initial }`). Le CSS de YouTube ne les casse pas et le nôtre ne fuit pas dans la page.
- **Mascotte et animations**. La mascotte est un SVG dessiné en code (`overlay/character.ts`, dégradés « pâte à modeler »), animé avec la Web Animations API : visée, lancer en parabole, éclaboussures, célébration, sommeil quand aucun profil n'existe. Elle est déplaçable et sa position est mémorisée. Elle respecte `prefers-reduced-motion`. Les polices Fredoka et Nunito Sans (`@fontsource`) sont servies depuis `public/fonts`.
- **Détection robuste**. La détection combine un `MutationObserver`, le scroll, les événements SPA de YouTube (`yt-navigate-finish`…) et un balayage toutes les 1,5 s. Elle gère aussi le recyclage des éléments : quand une tuile réaffiche une autre vidéo, son état est réinitialisé.

### Outillage et tests
- **oxlint** (`npm run lint`) : linter rapide pour `extension/src`.
- **pytest + pytest-asyncio** : Holo, Linkup et la session H sont injectés (`holo_fn`, `linkup_fn`, `SESSION_FACTORY`), donc aucun appel réseau. Les tests couvrent :
  - le batching et le cache ;
  - le refine parallèle ;
  - les exemples tirés des retours et l'invalidation du cache ;
  - la fusion des résultats Linkup dans le profil ;
  - la sérialisation de la file H et l'exposition de `agent_view_url` ;
  - le fait que `/health` n'expose aucun secret ;
  - les garde-fous de l'instruction `/train` ;
  - le pool de remplacements.
- **Playwright** (`tests/e2e.mjs`) lance Chromium avec l'extension non empaquetée. Il vérifie sur les fixtures :
  - les tuiles masquées ;
  - les badges « ? » ;
  - l'absence de tache sur les tuiles dans le sujet ;
  - l'annulation ;
  - le lancer manuel ;
  - la vitesse et le recyclage sur un fil dense.

  Captures dans `/tmp/tomate-shots`. Les autres scripts de `tests/` sont des scripts exploratoires (vrai YouTube, captures d'images).
- **Fixtures** (`fixtures/`) : fausses pages YouTube, TikTok et Instagram, un fil YouTube dense et un `harness.html` pour piloter la mascotte. Elles sont servies par `python3 -m http.server 8899`.

## Endpoints du backend

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/health` | État, présence des clés (booléens uniquement), modèles, `fake_ai` |
| POST | `/profile` | Texte libre → `TopicProfile` (Holo smart + Linkup) ; lance les pools de remplacements |
| GET | `/profile_progress/{pid}` | Étape en cours : `holo` / `linkup` / `done` |
| POST | `/classify` | Lot de `VideoMeta` → verdicts `on`/`off`/`unsure` (cache + Holo fast) |
| POST | `/classify/refine` | Re-vérifie les incertaines (Linkup + Holo fast) |
| POST | `/feedback` | `tomato` / `auto_tomato` / `undo` ; invalide le verdict en cache |
| POST | `/replacements` | Vidéos dans le sujet pour une plateforme (Linkup + oEmbed + scout, filtrées par le classifieur) |
| POST | `/train` | Job H : entraîner l'algo sur le compte (vidéos tomatées non annulées) |
| POST | `/scout` | Job H : repérer des vidéos dans le sujet sur le fil |
| POST | `/login` | Job H : attendre que l'utilisateur se connecte via Agent View |
| GET | `/jobs`, `/jobs/{id}` | État des jobs, `agent_view_url`, résultat |
| POST | `/local/open-browser` | Ouvre le Chrome d'entraînement dédié pour se connecter (chemin macOS) |
| POST | `/local/attach-browser` | Relance ce Chrome avec `--remote-debugging-port=9222` (non utilisé par l'UI) |

## Installation, lancement, tests

**Prérequis.** Il faut Python 3.12 avec uv, Node.js avec npm, et Google Chrome. Créer un `.env` à la racine qui définit `HAI_API_KEY`, `LINKUP_API_KEY` et `GLADIA_API_KEY`. Ce fichier n'est jamais commité ; `backend/app/config.py` le charge.

```bash
cd backend && uv sync
cd extension && npm install && npm run build      # prod
cd extension && npm run build:dev                 # + http://localhost:8899/* pour les fixtures
```

Ensuite, charger `extension/dist/` dans `chrome://extensions` (mode développeur), puis cliquer sur l'icône Tomate pour ouvrir le panneau.

```bash
./dev.sh
# fixtures :8899 + backend RÉEL :8787 + backend FAKE_AI :8790
```

- Fixtures de démo : `http://localhost:8899/{youtube,tiktok,instagram}.html`.
- Créer un profil dans le panneau, ou exécuter `chrome.storage.local.set({profileId:"<id>"})`.
- Pour la démo sans clés, saisir `http://localhost:8790` comme URL du backend dans le panneau.

```bash
cd backend && uv run pytest                       # aucun réseau
cd extension && npm run build && npm run lint
cd tests && npm install && node e2e.mjs           # E2E Playwright
```

Le script E2E crée le profil via `:8790`, alors que l'extension appelle `:8787` par défaut. Les deux processus partagent `backend/data`. Pour un run entièrement simulé, il faut les fixtures sur `:8899`, l'extension en `build:dev`, et le backend en `FAKE_AI=1` sur les deux ports.

## Structure du repo

```
backend/
  app/main.py              routes FastAPI, CORS, démarrage du worker H
  app/config.py            réglages (pydantic-settings, ../.env)
  app/models.py            schémas : TopicProfile, VideoMeta, Verdict, Job…
  app/store.py             persistance JSON + cache des verdicts
  app/core/holo.py         client Holo (OpenAI-compatible, sorties structurées)
  app/core/linkup.py       wrappers Linkup (structured / searchResults)
  app/core/profile.py      construction du profil
  app/core/classify.py     classification + refine
  app/core/replacements.py pool de remplacements
  app/core/h_jobs.py       file de jobs H Agents + instructions
  app/core/__init__.py     heuristiques FAKE_AI
  tests/                   pytest
  data/                    (ignoré par git) profils, retours, cache, logins
extension/
  src/manifest.ts          manifest MV3
  src/sw.ts                service worker
  src/content/             index.ts (orchestration), adapters.ts, ytPool.ts, replacements.ts
  src/overlay/             overlay.ts (mascotte, lancers, voiles), character.ts (SVG)
  src/panel/               side panel React
  src/shared/api.ts        types partagés + backendFetch
  public/fonts/            Fredoka, Nunito Sans
fixtures/                  fausses pages de fil + harness
tests/                     E2E Playwright + scripts exploratoires
dev.sh                     lance fixtures + backends
```

## Limites et points d'attention

- **Secrets**. Les clés vivent uniquement dans `.env`, qui est ignoré par git. `/health` ne renvoie que des booléens, et un test le vérifie.
- **Compte réel**. `/train`, `/scout` et `/login` agissent sur le vrai compte de l'utilisateur. Il ne faut les lancer qu'avec son accord explicite. En mode simulé, les boutons correspondants sont désactivés.
- **Actions autorisées : connu, à corriger**. Le panneau envoie `actions` (Pas intéressé / Recherches + visionnages / Likes) dans le corps de `/train`, mais `TrainReq` ne déclare pas ce champ. Il est donc ignoré, et l'instruction inclut toujours les trois actions. `build_instruction` sait déjà les filtrer : il reste à faire passer `actions` jusqu'au `payload` du job.
- **Mémoire**. Les jobs H et les pools de remplacements sont perdus au redémarrage du backend. Le cache des verdicts, lui, est persisté.
- **Sélecteurs DOM**. Les adaptateurs dépendent du DOM actuel de YouTube, TikTok et Instagram. Ces sélecteurs sont fragiles par nature. Les remplacements Instagram ne sont pas vérifiés par oEmbed.
- **`/local/*`**. Ces routes supposent macOS (chemin de Chrome codé en dur). `/login` n'a pas de bouton dans le panneau.
