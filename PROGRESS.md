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

## In Progress

- None.

## Next Suggested Items

- Add database and Redis real client initialization with startup checks.
- Add JSON structured logging output for log ingestion systems.
- Add frontend auth pages and route guards.
- Add email verification and forgot-password flow.
