# Project Progress

Last update: 2026-03-04

## Completed

- Established frontend-backend separated scaffold.
- Frontend: Vue 3 + Vite + TypeScript + Element Plus + VueUse Motion.
- Backend: FastAPI with uv-managed environment and tests.
- Added backend configuration loading from `.env` for PostgreSQL and Redis JDBC-style values.
- Refactored backend into layered structure under `backend/app/`.
- Added centralized logging module and request logging middleware.
- Improved logging lifecycle with guaranteed usage:
  - request started log
  - request finished log
  - request failed log
  - per-request `X-Request-ID` response header
- Implemented Auth V1 backend features:
  - register
  - login (username or email)
  - refresh token rotation
  - change password
  - logout
  - current user info (`/api/auth/me`)
- Added auth infrastructure:
  - SQLAlchemy async user model/session
  - Redis refresh-token store
  - JWT + password hashing security module
  - auth route integration tests
- Implemented frontend auth experience with unified Neo Terminal design language:
  - Login / Register / Profile pages
  - Vue Router auth guards (guest-only + requires-auth)
  - Pinia auth store with token persistence and session hydration
  - Route-level redirect handling after login
- Added password UX/security enhancements:
  - Register page now requires password confirmation
  - Password strength bars (weak/medium/strong) for register and change-password flows
  - Profile page now navigates to a dedicated change-password page instead of inline form
- Backend startup now auto-checks and creates required tables (`users`) if missing.
- Backend startup now also supports auto-creating missing target database before schema creation.
- PostgreSQL config now supports `database.schema` target (example: `DreamBoDB.stockdb`) and auto-creates missing schema.
- Added adaptive login captcha protection:
  - After repeated login failures, backend requires captcha
  - New captcha challenge API (`GET /api/auth/captcha`)
  - Login supports optional captcha fields (`captcha_id`, `captcha_code`)
  - Frontend login page now shows captcha challenge with fade transition and refresh action
  - Added backend/frontend test coverage for captcha flow and error payload handling
- Added frontend i18n foundation:
  - Introduced `vue-i18n` with `zh-CN` + `en-US` locale packs
  - Default locale is Chinese (`zh-CN`)
  - Added top-nav language switch with persisted locale preference (`app.locale`)
  - Migrated App/Home/Login/Register/Profile/ChangePassword UI strings to i18n keys
- Implemented email verification for account security:
  - Register now requires an email verification code before user creation
  - Change-password now requires current password + email verification code
  - Added email-code send endpoints for register/change-password flows
  - Added password-changed email notice after successful password updates
  - Added frontend email-code UX (send action, countdown, localized errors)
- Implemented forgot-password reset flow:
  - Added reset-password email-code send endpoint
  - Added reset-password endpoint with email code + new password
  - Added dedicated frontend reset-password view and login-page entry
- Hardened refresh-token session revocation for credential security events:
  - Password change now revokes all existing refresh tokens of that user
  - Password reset now revokes all existing refresh tokens of that user
  - Added integration tests to verify old refresh tokens return `401` after both flows
- Upgraded health endpoint to real probes:
  - Added `GET /api/health/liveness` for process-level alive checks
  - Added `GET /api/health/readiness` for PostgreSQL/Redis/SMTP readiness checks
  - Introduced readiness status grading (`ok | degraded | fail`) with per-service latency and error type
- Implemented stock data closed-loop (real data instead of mock):
  - Added stock tables: `stock_instruments`, `stock_daily_snapshots`, `stock_sync_cursors`
  - Integrated Tushare gateway and sync service for recent trade-day incremental sync
  - Added internal sync command: `uv run python scripts/sync_stocks.py`
  - Added stock APIs for list/search, detail, and daily snapshots
  - Replaced frontend home mock cards with backend data and keyword search
  - Added stock detail page with latest snapshot and recent daily rows
  - Added backend/frontend test coverage for stock routes, sync service, and stock views
- Added user-level RBAC and admin control surface:
  - Added `user_level` (`user/admin`) to user model and auth payloads
  - Added admin-only APIs for listing users and creating users with target level
  - Added startup seed flow for first admin via `INIT_ADMIN_*` env configuration
  - Added frontend admin route guard (`requiresAdmin`) and admin console page
  - Added backend/frontend test coverage for admin auth boundaries and navigation
- Added admin stock management surface:
  - Added admin-only full stock sync endpoint `POST /api/admin/stocks/full` with `list_status` filter
  - Added admin-only default stock query endpoint `GET /api/admin/stocks` with DB pagination
  - Added admin control hub page (`/admin`) to route into user/stock management
  - Updated stock admin center: full-fetch button now syncs to DB, default query uses paged DB API
  - Added frontend admin stock management page and top-nav entry to admin hub for quick access
  - Kept existing `/api/stocks` public dashboard API unchanged for compatibility
- Upgraded stock basic library model and sync strategy:
  - Expanded `stock_instruments` fields based on Tushare `stock_basic` (fullname/enname/cnspell/curr_type/act_name/act_ent_type)
  - Full stock basic sync now covers explicit `L/D/P/G` statuses
  - `GET /api/stocks` now defaults to `L` and supports explicit `list_status` filter (`ALL` or `L,D,P,G`)
  - Added authenticated trigger endpoint `POST /api/stocks/sync/full` for full stock basic refresh
  - Added compatibility schema patch step for legacy databases to auto-add newly required stock columns
- Upgraded dashboard stock browsing experience:
  - Added infinite scrolling on the home waterfall/grid with prefetch-trigger (`IntersectionObserver`)
  - Stabilized card rendering by deduplicating appended pages by `ts_code` to avoid old-card mutation on scroll
  - Reworked home stock cards to horizontal list arrangement while keeping vertical content flow inside each card
  - Reduced scroll repaint cost by simplifying fixed background layers and removing heavy visual effects

## In Progress

- None.

## Next Suggested Items

- Add database and Redis real client initialization with startup checks.
- Add JSON structured logging output for log ingestion systems.
- Add stock historical backfill task with batching, checkpoint resume, and retry strategy.
