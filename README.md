# Buzzer Game

A Jackbox-inspired real-time party quiz platform built for classroom use. A **Host** displays game state on a large screen while **Players** join and answer questions from their mobile browsers.

- Up to 250 players per room, 50 concurrent rooms
- Six question types: multiple choice, true/false, fill in the blank, multi-select, **Pin It** (tap a point on a coordinate grid or a picture) and **Estimate** (guess a number; closer earns more)
- Images in questions: a picture with any prompt, picture answer options, and Pin It on a picture, from each course's image library
- Light and dark themes in all three apps, following the device until toggled, with every colour pair contrast-checked (see [Light and dark themes](#light-and-dark-themes))
- Two grading modes: accuracy-based and participation-based (completeness)
- An optional per-question poll (👍 / 👎 / 🚩 "this was hard") with counts on the host's Game Over and a private per-player session report under Manage → Sessions
- Local accounts and guest players (no account required)
- Live answer distribution, per-player scoring

## Prerequisites

| Tool | Minimum version | Purpose |
|---|---|---|
| Docker Engine / Docker Desktop | 25 / 4.x | Running the full stack |
| Node.js | 20 | Frontend development servers |
| Python | 3.12 | Integration tests (optional if using Docker only) |

---

## First-time setup

### 1. Copy and configure environment

```bash
cp .env.example .env
```

Open `.env` and set:

| Variable | What to do |
|---|---|
| `MYSQL_ROOT_PASSWORD` | Choose a strong password |
| `MYSQL_PASSWORD` | Choose a strong password (used by the app) |
| `DATABASE_URL` | Update `change_me_app` to match `MYSQL_PASSWORD` |
| `ADMIN_USERNAME` | Username for the first admin account |
| `ADMIN_PASSWORD` | Password for the first admin account |
| `JWT_PRIVATE_KEY` | See step 2 |
| `JWT_PUBLIC_KEY` | See step 2 |

### 2. Create the Python virtual environment

Run the included setup script once after cloning. It creates `.venv`, installs all dependencies, and patches the activate script so your `.env` variables load automatically whenever the environment is activated:

```bash
bash scripts/setup_venv.sh
```

Then activate the environment (do this at the start of every terminal session):

```bash
source .venv/bin/activate        # macOS / Linux
```

Your shell prompt will show `(.venv)` when the environment is active, and variables like `ADMIN_USERNAME` and `ADMIN_PASSWORD` will already be set from your `.env`. All `python`, `pip`, `pytest`, and `alembic` commands below assume the environment is active.

> **Tip:** Most IDEs (VS Code, PyCharm) can detect `.venv` automatically and activate it for you in integrated terminals. In VS Code, open the Command Palette → *Python: Select Interpreter* and choose the `.venv` entry.

> **Windows:** The setup script targets bash (macOS/Linux). On Windows, create the venv manually (`python3.12 -m venv .venv`), install dependencies (`pip install -r backend/requirements.txt -r tests/integration/requirements.txt`), and load `.env` variables in your shell before running any scripts.

### 3. Generate JWT signing keys

The backend signs tokens with RS256. Run the included helper to generate a key pair and print the values ready to paste into `.env`:

```bash
# With the virtual environment active (cryptography is already installed):
python backend/scripts/generate_keys.py

# Or via Docker (no local Python required):
docker run --rm python:3.12-slim \
  sh -c "pip install cryptography -q && python" \
  < backend/scripts/generate_keys.py
```

Paste the two `JWT_*` lines into `.env`.

### 4. Install frontend dependencies and build

A root-level `package.json` manages a `concurrently` dev tool and provides convenience scripts:

```bash
npm install            # installs concurrently (root dev tool)
npm run install:all    # installs dependencies in all three frontend apps
```

> **Note:** Running `npm run build` is only needed if you want the pre-built apps to be served by Nginx at `http://localhost:8080`. If you plan to use the Vite dev servers (the typical workflow), you can skip the build step entirely.

> **Note:** If the build fails with `EACCES: permission denied` on the `dist` directory, Docker likely created it as root before the build ran. Fix with: `sudo chown -R $(id -u):$(id -g) frontend/*/dist`

### 5. Start the Docker stack

```bash
docker compose up
```

On first run, Docker builds the backend image and pulls MySQL, Redis, and Nginx. MySQL takes ~30 seconds to become healthy before the backend starts.

Use `--build` any time you change `requirements.txt` or the `Dockerfile`:

```bash
docker compose up --build
```

> **First run note:** On initial startup, MySQL takes 30–45 seconds to initialize the database user, and the backend will **wait — logging `admin_bootstrap_waiting_for_schema` every few seconds — until you run the migrations in the next step**, because its startup needs the database schema, which doesn't exist yet. Both behaviors are normal.

### 6. Run database migrations

Apply the Alembic schema migrations (this runs in its own one-off container, so it works while the backend is still waiting):

```bash
docker compose run --rm backend alembic upgrade head
```

This creates all tables. Within a few seconds the waiting backend picks up the new schema, finishes starting, and bootstraps the admin account from `ADMIN_USERNAME`/`ADMIN_PASSWORD` — no manual step needed.

---

## Accessing the application

| Interface | URL | Notes |
|---|---|---|
| Player app | http://localhost:8080/player/ | Mobile-optimised |
| Host app | http://localhost:8080/host/ | Large-screen display |
| Admin app | http://localhost:8080/admin/ | Course/game/user management |
| API (direct) | http://localhost:8000 | Bypasses Nginx |
| Interactive API docs | http://localhost:8000/api/docs | Swagger UI (dev only) |
| Health check | http://localhost:8000/api/health | Service status |

Log in to the Host or Admin app with the `ADMIN_USERNAME` / `ADMIN_PASSWORD` you set in `.env`.

---

## Development workflow

### Starting a session

Run these commands at the beginning of every development session.

**1. Activate the Python virtual environment** in any terminal where you will run Python tools (tests, migrations, scripts):

```bash
source .venv/bin/activate
```

If you ran `scripts/setup_venv.sh` during first-time setup, this also loads all your `.env` variables automatically (e.g. `ADMIN_PASSWORD`). This is not needed for the Docker stack itself — the backend runs inside its own container. It is needed whenever you run `pytest`, `alembic`, or any Python script directly in your terminal.

**2. Start the Docker stack** (backend, MySQL, Redis, Nginx):

```bash
docker compose up
```

The backend mounts `./backend` and runs with `--reload`, so any Python change takes effect immediately — no restart needed. Logs stream to the terminal.

**3. Start all frontend dev servers** in a single terminal from the repo root:

```bash
npm run dev
```

This starts all three Vite dev servers concurrently with color-coded, labeled output. **Check the terminal output for the exact URLs** — Vite picks the next available port if the default is already in use, so the numbers may differ from the typical defaults shown below:

```
[host]   VITE ready  →  http://localhost:5173
[player] VITE ready  →  http://localhost:5174
[admin]  VITE ready  →  http://localhost:5175
```

Press `Ctrl+C` once to stop all three.

To start a single app instead:

```bash
npm run dev:host    # typically http://localhost:5173
npm run dev:player  # typically http://localhost:5174
npm run dev:admin   # typically http://localhost:5175
```

In each case, check the terminal output for the actual URL Vite is listening on.

The Vite dev servers watch your source files and hot-reload the browser instantly on every save — no manual rebuild step. They proxy `/api` traffic to the Docker backend, so the full stack works at these ports during development.

> **Backend only?** If you are only changing Python code, you can skip the frontend dev servers and use the pre-built apps at `http://localhost:8080/host/`, `http://localhost:8080/player/`, and `http://localhost:8080/admin/` instead.

### During a session

- **Backend changes** — saved automatically; uvicorn reloads the process within a second.
- **Frontend changes** — saved automatically; the browser hot-reloads via the Vite dev server.
- **Database model changes** — generate and apply a migration:

```bash
docker compose exec backend alembic revision --autogenerate -m "describe change"
docker compose exec backend alembic upgrade head
```

### Ending a session

When you are done, stop all running processes:

- Press `Ctrl+C` in each terminal running a Vite dev server.
- Stop the Docker stack:

```bash
docker compose down
```

If you made frontend changes during the session and want `localhost:8080` to reflect them (e.g. for integration testing), run a final build before stopping:

```bash
npm run build
```

### Other migration commands

```bash
# Apply all pending migrations
docker compose exec backend alembic upgrade head

# Revert the last migration
docker compose exec backend alembic downgrade -1
```

---

## Testing

### Integration test suite

Tests run against the live Docker stack (start it first). Dependencies are already installed if you followed the virtual environment setup above. Activate the environment, then run:

```bash
python -m pytest tests/integration/ -q
```

Include timer-expiry edge cases (sets `time_limit_seconds=2` so tests finish quickly):

```bash
python -m pytest tests/integration/ -q --fast
```

### WebSocket smoke test

A quick end-to-end script that creates seed data, plays through a full game, and verifies every event payload (dependencies are included in `backend/requirements.txt`):

```bash
python scripts/smoke_test_websocket.py
```

Override credentials or the target URL with environment variables:

```bash
ADMIN_USERNAME=admin ADMIN_PASSWORD=changeme123 BASE_URL=http://localhost:8000 \
  python scripts/smoke_test_websocket.py
```

### Theme token check

`scripts/check_theme_tokens.py` scans the three apps for colours that bypass the theme: raw
palette classes (`bg-slate-800`, `text-white`), `dark:` variants, focus-ring utilities that would
override the shared focus outline, colour literals, a repeated theme storage key, and text smaller
than `text-xl` on the projector screens (outside named exemptions). It exits non-zero on any
violation and runs as part of the unit tests:

```bash
python scripts/check_theme_tokens.py
PYTHONPATH=backend python -m pytest tests/unit -q
```

### UI screenshots

`scripts/capture_ui_screenshots.py` drives the real apps with Playwright and saves every named
screen and interaction state (54 of them: host, player and admin) in both color modes to
`docs/ui/after/{light,dark}/`.
It builds its own fixture course and games through the API, plays them with the Host UI, one
player page and two socket players, and deletes the fixtures at the end. It needs the Docker
stack and the three dev servers (`npm run dev`, ports 5173/5174/5175), plus its own dependencies:

```bash
pip install -r scripts/requirements-ui.txt
python -m playwright install chromium
python scripts/capture_ui_screenshots.py                       # all screens, both themes
python scripts/capture_ui_screenshots.py --only host-lobby,player-question-mc
```

### Simulate players

`scripts/simulate_players.py` populates a live room with realistic fake players so you can test the full game loop without real students. It creates temporary local accounts via the Admin API, connects them over WebSocket, and has them answer automatically. All dependencies are already installed by `scripts/setup_venv.sh`.

**Workflow:**

1. Start the Docker stack and open the Host app.
2. Create a room and note the room code shown in the lobby.
3. In a separate terminal (with the virtual environment active), run:

```bash
python scripts/simulate_players.py --room ABCDE1
```

4. Press **Start** / **Next** on the host screen to advance through questions. Players answer automatically. Late players join after their randomised delay and print a message when they arrive.
5. When the game ends, temporary accounts are deleted automatically.

**Player profiles** and default mix:

| Profile | Default % | Behaviour |
|---------|-----------|-----------|
| `fast` | 25 % | Answers in 0.5–3 s; rarely skips |
| `normal` | 35 % | Answers in 3–8 s; occasionally skips |
| `slow` | 20 % | Answers in 8–18 s; more likely to skip |
| `absent` | 10 % | Never submits an answer |
| `late` | 10 % | Waits 25–70 s before joining, then answers at a normal pace |

**Common options:**

```bash
# 40 players with a custom profile mix (remainder becomes "normal")
python scripts/simulate_players.py --room ABCDE1 --players 40 \
    --fast-pct 20 --slow-pct 20 --absent-pct 10 --late-pct 10

# Pass the exported game JSON so fast/normal players lean toward correct answers
python scripts/simulate_players.py --room ABCDE1 --players 30 \
    --game-json sample_games/my_quiz.json

# Custom fill-in-the-blank word pool (repeat a word to weight it higher)
python scripts/simulate_players.py --room ABCDE1 --players 25 \
    --fitb-words "spring,spring,summer,summer,summer,autumn,winter"

# Leave temporary accounts in the DB after the run (useful for inspecting scores)
python scripts/simulate_players.py --room ABCDE1 --keep
```

Admin credentials default to the `ADMIN_USERNAME` / `ADMIN_PASSWORD` environment variables loaded automatically by the virtual environment. Override them with `--admin-user` and `--admin-pass`, or point at a different backend with `--base-url http://localhost:8000`.

---

## Common operations

### Load the demo quiz

After running migrations, seed the database with a demo game that covers every question type and grading mode:

```bash
python scripts/seed_demo.py
```

This creates a **Demo Course** and a **Buzzer Demo** game with 9 questions (1 point each):

| # | Type | Grading | Question |
|---|------|---------|---------|
| 1 | Multiple choice | Accuracy | Which planet has the most moons? |
| 2 | True/False | Accuracy | A group of flamingos is called a 'flamboyance'. |
| 3 | Multiple choice | Completeness | What is your go-to comfort food? |
| 4 | Multiple choice | Accuracy | What is the largest land animal on Earth? |
| 5 | True/False | Accuracy | The Great Wall of China is visible from space. |
| 6 | True/False | Completeness | Do you prefer coffee over tea? |
| 7 | Fill in the blank | Accuracy (exact) | Chemical symbol for Gold? |
| 8 | Fill in the blank | Accuracy (fuzzy) | Who wrote 'Romeo and Juliet'? |
| 9 | Fill in the blank | Completeness | What country would you visit? |

### Admin interface

The Admin app (`http://localhost:8080/admin/`) is for admin-level tasks:

| Section | What you can do |
|---|---|
| **Users** | Create local accounts; click any user to grant or revoke course access (HOST/PLAYER) and game access. A game grant only works for a HOST of that game's course, so the UI offers only those games |
| **Courses** | Create and edit courses, including **guest access** (see below); open a course's roster in the Host app |
| **Guests** | View guest accounts; merge a guest's scores into a real netid account; delete stale guests |
| **Host tools** | Links to Games, Rosters, Sessions and Run a game in the Host app, where admins can act on every course |

Log in with the `ADMIN_USERNAME` / `ADMIN_PASSWORD` from your `.env`.

### Host management

Hosts manage their courses in the Host app (`http://localhost:8080/host/` → **Manage games & rosters**, or `/host/manage/`). Everything is scoped to courses where the user has HOST access; admins pass every check.

| Section | What you can do |
|---|---|
| **Games** | Pick a course; create games in it, import a game from a JSON file into it, edit or delete games (a game with a live room can't be deleted) |
| **Questions** | Add, edit, delete, and reorder questions and their scoring; export the game as a JSON file |
| **Rosters** | Upload a Canvas gradebook CSV or a basic CSV roster; activate or deactivate individual entries |
| **Images** | The course's image library: upload, view, replace or delete pictures used in its questions (see [Images in questions](#images-in-questions)) |
| **Sessions** | List the course's sessions; **View details** shows who answered what and each player's question feedback (private, see [Question feedback](#question-feedback)); for completed sessions, download the HTML summary and the per-player scores CSV (raw or Canvas gradebook) |

Every game belongs to exactly one course, chosen when it is created or imported. A host can run or edit a game only if they are a HOST of its course **and** have been granted that game (they are granted games they create automatically). Players are admitted by course roster/role, as before.

**Guest access** is set per course: *Roster emails only* (the default — a guest must use an email on the course roster and appears under their roster name), *Anyone with the room code* (for parties and open events), or *No guests*. A guest pass only works for the room it was issued for.

> Under `npm run dev` the Admin and Host apps run on different ports, so following an Admin "Host tools" link asks you to log in again. On the nginx build (`localhost:8080`) they share an origin and the login carries over. Set `VITE_HOST_APP_URL` if your Host dev server isn't on port 5173.

### Light and dark themes

All three apps have a light and a dark theme. A first visit follows the device's setting; the
**theme toggle** (moon / sun button) switches it, and the choice is remembered per browser
(`localStorage['buzzer-theme']`), so a projector laptop can stay light while phones follow their
own setting. Where the toggle is:

| App | Toggle |
|---|---|
| Host | Next to Logout in the `/manage` sidebar, beside Sign Out on Home, under the QR panel during a game, and top right on Login |
| Player | Top right on Join, Name, Login, the lobby and Game Over (not on question or results screens, so it can't be tapped by mistake while answering) |
| Admin | Next to Logout in the sidebar, and top right on Login |

Colours come from shared **theme tokens** in `frontend/shared/theme/` (role names such as
`surface`, `fg-muted`, `accent`, `success`, `answer-3`), not raw Tailwind colours. Every token
pair has a measured WCAG contrast in both themes (text ≥ 4.5:1, controls and graphics ≥ 3:1),
checked by `tests/unit/test_theme_contrast.py`. How to use or add a token:
[frontend/shared/theme/README.md](frontend/shared/theme/README.md).

### Question feedback

After answering, players see an optional **"Liked the question?"** poll under "Answer locked in!" and again on that question's results: thumbs up or down (one or neither) and a separate 🚩 flag, with the hint "Flag the question if it was hard — it lets your professor know." Tapping a pressed button clears it, and a player can change their mind until the game ends.

| Where | What the professor sees |
|---|---|
| Host **Game Over** breakdown (on the projector) | Counts only per question: 👍 n · 👎 n · 🚩 n |
| Session **HTML report** download | The same counts per question (the report stays free of names) |
| **Manage → Sessions → View details** | Private: per question, every player's answer, result, points, time and their 👍/👎/🚩, a "Flagged only" filter, and players ranked by points |

The detail page uses the same access rule as the session downloads.

### Quiz import and export

Games (metadata + all questions including answer data) can be exported and re-imported as JSON files. A game whose questions use images exports as **version 2**, with each image embedded (see [Images in questions](#images-in-questions)); every other game exports as version 1, exactly as before. Both versions import. A file can be at most **60 MB**.

**Export** — from the Host app, open a game's question editor and click **Export JSON**. Or via the API:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/admin/games/{game_id}/export" \
  -o my_quiz.json
```

**Import** — in the Host app's Games page, pick the course, click **Import JSON** and choose a `.json` file. This always creates a *new* game in that course — it never overwrites an existing one. The course is chosen at import time, not stored in the file, so version-1 files import unchanged. Or via the API (hosts use `/api/host/games/import` with the same fields):

```bash
curl -X POST "http://localhost:8000/api/admin/games/import" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@my_quiz.json" \
  -F "course_id=1"
```

The file format is:

```json
{
  "format": "buzzer/game",
  "version": 1,
  "game": { "title": "...", "description": "...", "max_players": 150 },
  "questions": [
    {
      "type": "multiple_choice",
      "grading_type": "ACCURACY",
      "prompt": "...",
      "time_limit_seconds": 30,
      "points_value": 1000,
      "config": { "options": ["A", "B", "C", "D"] },
      "answer_data": { "answer_points": [1000, 0, 0, 0] }
    }
  ]
}
```

Question order is determined by array position; `order_index` is assigned automatically on import.

#### Question types

Every type is defined once in `backend/app/services/question_types.py`, so create, update and import validate it identically. `COMPLETENESS` questions give full `points_value` for any valid answer and need no answer data (`{}`) except where noted.

| `type` | `config` | `answer_data` (ACCURACY) | Scoring |
|---|---|---|---|
| `multiple_choice` | `{"options": [...]}` (≥ 2) | `{"answer_points": [...]}` (one per option, ≥ 0) | Points of the chosen option |
| `true_false` | `{}` | `{"answer_points": {"true": n, "false": n}}` | Points of the chosen value |
| `fill_in_the_blank` | `{"maxLength": n}` (optional) | `{"acceptedAnswers": [...], "answerPoints": [...], "editDistance": n}` | Best accepted answer within `editDistance` typos (case and spacing ignored) |
| `multi_select` | `{"options": [...]}` (≥ 2) | `{"answer_points": [...]}` (negative = penalty) | Sum of chosen options, floored at 0 |
| `pin_drop` | `{"grid": {"xMin", "xMax", "yMin", "yMax", "step"}, "snap": bool}` | `{"target": {"x", "y"}, "fullRadius": n, "zeroRadius": n}` | Distance-based (below) |
| `estimate` | `{"unit": "years", "integer": bool}` (both optional) | `{"answer": n, "tolerance": {"mode": "relative" \| "absolute", "full": n, "zero": n}}` | Distance-based (below) |

**Distance-based scoring (`pin_drop`, `estimate`).** Full `points_value` when the answer is within `full` of the target, falling linearly to 0 at `zero`, rounded to 2 decimals; the answer counts as *correct* when it is within `full`. For `pin_drop` the distance is the straight-line distance in grid units; for `estimate` it is `|guess − answer|` (`absolute`) or that as a percentage of the answer (`relative`; needs a non-zero answer). Use `absolute` for years and small ranges — 2015 is only 0.5 % away from 2005.

**`pin_drop` grid rules.** All numbers within ±1000, `min < max`, each range a whole number of `step`s, at most 20 cells per axis and an x:y range ratio between 1:2 and 2:1 (so the grid stays usable on a phone). With `snap`, pins land on grid intersections. The target must be inside the grid and `0 ≤ fullRadius < zeroRadius`.

**Players never see answer data.** Before the reveal they receive only `grid`/`snap` or `image` (`pin_drop`) or `unit`/`integer` (`estimate`) from `config`, plus image ids (`promptImageId`, `optionImages`), which reveal nothing. Players send `{"point": {"x": n, "y": n}}` or `{"value": n}`; malformed answers (outside the grid, not finite, a fraction when `integer`) are rejected and not scored.

Example questions:

```json
{
  "type": "pin_drop",
  "grading_type": "ACCURACY",
  "prompt": "Plot the vertex of y = (x - 3)² - 4",
  "time_limit_seconds": 30,
  "points_value": 1000,
  "config": { "grid": { "xMin": -10, "xMax": 10, "yMin": -10, "yMax": 10, "step": 1 }, "snap": true },
  "answer_data": { "target": { "x": 3, "y": -4 }, "fullRadius": 1, "zeroRadius": 5 }
}
```

```json
{
  "type": "estimate",
  "grading_type": "ACCURACY",
  "prompt": "In what year did humans first land on the Moon?",
  "time_limit_seconds": 20,
  "points_value": 1000,
  "config": { "unit": "year", "integer": true },
  "answer_data": { "answer": 1969, "tolerance": { "mode": "absolute", "full": 0, "zero": 8 } }
}
```

#### Images in questions

Each course has an **image library** (Host app → **Images**, or the picker in the question editor). Any HOST of the course can upload, replace and delete its images; admins can too.

- **Formats and limits:** PNG, JPEG, GIF or WebP, up to 5 MB. Every upload is decoded and re-encoded: it is shrunk to at most 1600 px on its longest side, its metadata (including phone GPS locations) is removed, EXIF rotation is applied, and animations keep only their first frame. Uploading the same picture twice returns the existing image. A course may store up to 200 MB of images.
- **Links:** images are served at `/api/images/{id}` without login, so `<img>` tags work on every screen. The 32-character id is unguessable, but anyone who has a link can view that image.
- **In use:** an image can't be deleted while a question uses it (the error lists the questions), and it can't be replaced while a game that uses it has a live room. Replacing keeps the id, so every question picks up the new picture; past reports show it too.

Questions reference images by id in `config` (never in `answer_data`):

| Key | Types | Meaning |
|---|---|---|
| `promptImageId` | every type | A picture shown under the prompt on the projector (phones don't show the prompt) |
| `optionImages` | `multiple_choice`, `multi_select` | One image id or `null` per option, exactly as long as `options`; the option text stays required and is the picture's alt text |
| `image` | `pin_drop` | `{"imageId": "..."}` instead of `grid`: players pin on the picture. The server adds the picture's `width`/`height` |

Every referenced image must be in the game's course, or the save is rejected (422).

**Pin It on a picture.** Coordinates are fractions of the image: `x` from 0 (left) to 1 (right), `y` from 0 (top) to 1 (bottom). The target must be inside `[0, 1]`, and the radii are fractions of the image **width**, with `0 ≤ fullRadius < zeroRadius ≤ 1.5`. Distances count a vertical step at its true size (`hypot(Δx, Δy × height / width)`), so the scoring circles stay round on a wide picture. `snap` isn't available on a picture.

```json
{
  "type": "pin_drop",
  "grading_type": "ACCURACY",
  "prompt": "Where is Madison?",
  "time_limit_seconds": 30,
  "points_value": 1000,
  "config": { "image": { "imageId": "3f2a9c1e8b7d4e6fa0c5d2b1e9f8a7c6" } },
  "answer_data": { "target": { "x": 0.62, "y": 0.41 }, "fullRadius": 0.03, "zeroRadius": 0.12 }
}
```

**Version 2 files.** An export adds an `images` list with one entry per referenced image, `{"ref", "filename", "contentType", "data"}`, where `data` is base64 and every image reference in the questions is a `ref`. On import each entry is decoded and processed like an upload into the **target course** (so it gets a new id), and the references are rewritten. Hand-made files may use any `ref` label (1–64 characters). An import may embed at most 100 images; a bad entry or a reference to a missing `ref` is rejected with a 422 naming it, and nothing is created. A version-1 file must not contain `images`. PNG and GIF images come back byte-for-byte; JPEG and WebP are re-encoded on every import, so they lose a little quality each round trip.

**The session report** embeds thumbnails (at most 480 px wide) of the prompt, option and Pin It images, so it still works offline.

**Deployment notes.**
- **Rebuild after pulling:** image processing needs Pillow, a new backend dependency. Run `docker compose up --build`, and `pip install -r backend/requirements.txt -r tests/integration/requirements.txt` in your virtual environment.
- **Proxies:** the bundled nginx allows 64 MB request bodies and a 300 s read timeout on `/api/` (a large import can take a while). Any other proxy in front of `/api/` needs the same two settings, and must let `/api/images/` through without login.
- **Memory:** images are processed one at a time, and one job can use about 225 MB at peak (a 25-megapixel PNG; JPEGs up to 50 MP use far less). Give the backend container at least 512 MB of headroom.

### Export session scores

After a game session completes, its host, anyone who manages its game, or an admin can download a CSV of all player scores (Host app → Sessions, or via the API; `format=raw` or `canvas`), and an HTML summary from `/report`:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/host/sessions/{session_id}/export?format=raw" \
  -o scores.csv
```

Columns: `Player, Q1, Q2, …, Qn, Total`.

### Import a course roster

Roster uploads expect either a minimal CSV roster or a **Canvas gradebook export CSV**. When importing, the user can match columns to necessary fields for the players.

See `sample_rosters/*sample_roster_from_gradebook*.csv` for a working examples. Upload via the Host app (Manage → Rosters → pick the course → Upload CSV), or via the API (hosts use `/api/host/courses/{course_id}/roster`):

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -X POST "http://localhost:8000/api/admin/courses/{course_id}/roster" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@sample_rosters/sample_roster_from_gradebook.csv"
```

### View structured logs

```bash
docker compose logs -f backend       # stream backend logs
```

### Reset the database (destructive)

```bash
docker compose down -v               # removes the MySQL volume
docker compose up --build
docker compose run --rm backend alembic upgrade head   # the waiting backend finishes startup on its own
```

---

## Project structure

```
buzzer/
├── backend/
│   ├── app/
│   │   ├── routers/        HTTP endpoints  (auth, game, admin, host, images, health)
│   │   ├── services/       Business logic  (auth, game, state, roster, export, content, question types, images, report)
│   │   ├── websocket/      Socket.io gateway and JWT middleware
│   │   ├── models/         SQLAlchemy ORM models
│   │   ├── schemas/        Pydantic request/response schemas
│   │   └── migrations/     Alembic schema migrations
│   ├── scripts/
│   │   └── generate_keys.py   RS256 key-pair generator
│   └── requirements.txt
├── frontend/
│   ├── host/               React app — host/display screen  (typically port 5173 in dev)
│   ├── player/             React app — player mobile browser (typically port 5174 in dev)
│   ├── admin/              React app — admin management UI   (typically port 5175 in dev)
│   └── shared/theme/       Light/dark theme tokens, base styles and Tailwind preset (all three apps)
├── nginx/
│   └── nginx.dev.conf      Reverse-proxy config
├── mysql-init/             SQL scripts run by MySQL on first startup
├── scripts/
│   ├── smoke_test_websocket.py   End-to-end WebSocket smoke test
│   ├── simulate_players.py       Multi-profile async player simulator
│   ├── seed_demo.py              Seeds a demo course and game
│   ├── check_theme_tokens.py     Rejects colours that bypass the theme tokens
│   └── capture_ui_screenshots.py Captures every UI screen in light and dark
├── tests/
│   ├── unit/               Pytest unit tests (no Docker needed; incl. theme contrast and token checks)
│   └── integration/        Pytest integration test suite
├── docs/
│   └── ui/                 UI screenshots (light, dark and visual themes)
├── sample_games/           Example game JSON files for import
├── sample_rosters/         Example Canvas gradebook CSV files for roster import
├── docker-compose.yml
└── .env.example            Copy to .env and fill in before first run
```

---

## Architecture overview

```
Browser (HTTP)
      │
      ▼
   Nginx :8080
   ├── /api/*      → FastAPI backend :8000
   ├── /socket.io/ → FastAPI backend :8000  (WebSocket upgrade)
   ├── /host/      → Host React app   (static)
   ├── /player/    → Player React app (static)
   └── /admin/     → Admin React app  (static)
                          │
                     FastAPI :8000
                     ├── SQLAlchemy → MySQL :3306
                     └── redis-py   → Redis :6379
```

Real-time communication uses **Socket.io** (python-socketio on the server, socket.io-client in the browser). Game state is stored in Redis for low-latency reads; every player answer is immediately persisted to MySQL.

---

## Credits

Built by [Aryan Maheshwari](https://github.com/arymaheshwari).
