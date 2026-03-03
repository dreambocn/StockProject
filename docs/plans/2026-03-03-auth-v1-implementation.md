# Auth V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement user registration, login, refresh token rotation, password change, logout, and current-user API for the FastAPI backend.

**Architecture:** Use SQLAlchemy async with PostgreSQL for user persistence, JWT for stateless access tokens, and Redis for refresh-token lifecycle management. Keep auth logic in a service layer and expose routes under `/api/auth`, reusing existing request logging middleware.

**Tech Stack:** FastAPI, SQLAlchemy async, asyncpg, redis-py asyncio, pwdlib (argon2), PyJWT, pytest

---

### Task 1: Add auth dependencies and settings

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/settings.py`
- Modify: `backend/.env.example`

### Task 2: Build persistence and cache abstractions

**Files:**
- Create: `backend/app/db/base.py`
- Create: `backend/app/db/session.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/cache/token_store.py`
- Create: `backend/app/cache/redis.py`

### Task 3: Implement security and auth service layer

**Files:**
- Create: `backend/app/core/security.py`
- Create: `backend/app/services/auth_service.py`

### Task 4: Implement auth HTTP layer

**Files:**
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/api/deps/auth.py`
- Create: `backend/app/api/routes/auth.py`
- Modify: `backend/app/main.py`

### Task 5: Add TDD integration tests

**Files:**
- Create: `backend/tests/test_auth_routes.py`

### Task 6: Update docs and progress tracking

**Files:**
- Modify: `README.md`
- Modify: `PROGRESS.md`
