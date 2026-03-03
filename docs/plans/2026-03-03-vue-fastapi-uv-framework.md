# Vue + FastAPI Framework Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a frontend-backend separated starter framework with Vue + Vite (component library + motion) and FastAPI managed by uv.

**Architecture:** Use two top-level apps: `frontend/` for Vue SPA and `backend/` for FastAPI service. Frontend reads API base URL from env and calls backend `/api/*` endpoints; backend exposes health and sample stock APIs with CORS enabled for local frontend.

**Tech Stack:** Vue 3, Vite, TypeScript, Element Plus, @vueuse/motion, FastAPI, uv, pytest, Vitest

---

### Task 1: Scaffold frontend app

**Files:**
- Create: `frontend/*` (via Vite scaffold)

**Step 1: Generate project skeleton**

Run: `npm create vite@latest frontend -- --template vue-ts`

**Step 2: Install base dependencies**

Run: `npm install` (inside `frontend`)

**Step 3: Add UI and motion dependencies**

Run: `npm install element-plus @vueuse/motion pinia vue-router`

### Task 2: TDD for backend API

**Files:**
- Create: `backend/tests/test_main.py`
- Modify: `backend/main.py`

**Step 1: Write failing tests for `/api/health` and `/api/stocks`**

Run: `uv run pytest -q`
Expected: fail because endpoints are not implemented.

**Step 2: Implement minimal FastAPI app to pass tests**

Add app creation, CORS middleware, and both endpoints.

**Step 3: Re-run tests**

Run: `uv run pytest -q`
Expected: all pass.

### Task 3: TDD for frontend rendering and API integration boundary

**Files:**
- Create: `frontend/src/App.test.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/main.ts`

**Step 1: Write failing UI test**

Test checks dashboard heading and stock cards rendering from initial state.

**Step 2: Run test to verify failure**

Run: `npm run test -- --run`
Expected: fail before component implementation.

**Step 3: Implement minimal UI with Element Plus + motion directives**

Create dashboard layout, API-loading logic, and motion usage.

**Step 4: Re-run tests**

Run: `npm run test -- --run`
Expected: pass.

### Task 4: Developer experience and docs

**Files:**
- Create: `frontend/.env.example`
- Create: `README.md`

**Step 1: Add frontend env template**

Define `VITE_API_BASE_URL`.

**Step 2: Document run commands**

Document local start commands for both apps and project structure.

### Task 5: Final verification

**Step 1: Backend verification**

Run: `uv run pytest -q`

**Step 2: Frontend verification**

Run: `npm run test -- --run`

**Step 3: Build verification**

Run: `npm run build`
