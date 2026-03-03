# StockProject Fullstack Starter

Frontend and backend are separated:

- `frontend/`: Vue 3 + Vite + TypeScript + Element Plus + VueUse Motion
- `backend/`: FastAPI managed by `uv`

Frontend auth pages and guards:

- `frontend/src/router/index.ts`: routes and auth guards
- `frontend/src/stores/auth.ts`: token persistence and auth state
- `frontend/src/views/LoginView.vue`: login page
- `frontend/src/views/RegisterView.vue`: register page
- `frontend/src/views/ProfileView.vue`: user profile and password change

Backend structure:

- `backend/main.py`: dev entrypoint (keeps `fastapi dev main.py` compatible)
- `backend/app/main.py`: FastAPI app wiring (middleware, routers)
- `backend/app/api/routes/`: API route modules (`health.py`, `stocks.py`, `auth.py`)
- `backend/app/core/settings.py`: env/settings parsing (PostgreSQL, Redis)
- `backend/app/core/logging.py`: centralized logging setup and request log helper
- `backend/app/core/security.py`: password hashing and JWT token handling
- `backend/app/services/auth_service.py`: user auth business logic

## Quick start

### One-click startup (Windows)

Run this in project root:

```bash
start-dev.bat
```

It opens two terminals automatically: backend and frontend dev servers.

### 1) Run backend

Backend reads database/cache settings from `backend/.env`.

Template: `backend/.env.example`

On startup, backend can auto-create the target database and required tables (controlled by `DB_AUTO_CREATE_DATABASE` and `DB_AUTO_CREATE_TABLES`).

PostgreSQL URL supports `database.schema` format, e.g. `jdbc:postgresql://host:port/DreamBoDB.stockdb`.

Login security controls in `backend/.env`:

- `LOGIN_CAPTCHA_THRESHOLD` (default: `2`)
- `LOGIN_FAIL_WINDOW_SECONDS` (default: `900`)
- `CAPTCHA_TTL_SECONDS` (default: `300`)
- `CAPTCHA_LENGTH` (default: `4`)

```bash
cd backend
uv run fastapi dev main.py
```

Backend default URL: `http://127.0.0.1:8000`

### Auth API

- `POST /api/auth/register`
- `POST /api/auth/login` (`account` supports username or email)
- `GET /api/auth/captcha`
- `POST /api/auth/refresh`
- `POST /api/auth/change-password`
- `POST /api/auth/logout`
- `GET /api/auth/me`

Captcha flow:

- After repeated failed logins (`LOGIN_CAPTCHA_THRESHOLD`), login requires captcha.
- `GET /api/auth/captcha` returns `{ captcha_id, image_base64, expires_in }`.
- `POST /api/auth/login` accepts optional `captcha_id` and `captcha_code`.
- Captcha-required failures return structured `detail` with `captcha_required` and `captcha_reason`.

### 2) Run frontend

```bash
cd frontend
npm run dev
```

Create `frontend/.env` from `frontend/.env.example` before running dev server.

Frontend default URL: `http://127.0.0.1:5173`

### Frontend i18n

- Added `vue-i18n` with `zh-CN` and `en-US` locales.
- Default locale is `zh-CN`.
- Language can be switched from the top navigation and is persisted to `localStorage` (`app.locale`).

## Test commands

Backend:

```bash
cd backend
uv run pytest -q
```

Frontend:

```bash
cd frontend
npm run test -- --run
```

## Build command

```bash
cd frontend
npm run build
```
