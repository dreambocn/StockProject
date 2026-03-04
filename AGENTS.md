# AGENTS.md
Repository guidance for autonomous coding agents working in `StockProject`.

## 1) Project Layout
- `backend/`: FastAPI app managed by `uv`
- `frontend/`: Vue 3 + Vite + TypeScript app
- `docs/plans/`: design/implementation plans
- `PROGRESS.md`: project milestone log
- Backend entrypoints: `backend/main.py`, `backend/app/main.py`
- Frontend entrypoints: `frontend/src/main.ts`, `frontend/src/App.vue`

## 2) Cursor / Copilot Rules Status
- `.cursorrules`: not found
- `.cursor/rules/`: not found
- `.github/copilot-instructions.md`: not found
- This `AGENTS.md` is the primary agent instruction source.

## 3) Setup Commands
Backend dependencies:
```bash
cd backend
uv sync
```
Frontend dependencies:
```bash
cd frontend
npm install
```
Run both (Windows):
```bash
start-dev.bat
```

## 4) Build / Lint / Test Commands
### Backend
Dev server:
```bash
cd backend
uv run fastapi dev main.py
```
All tests:
```bash
cd backend
uv run pytest -q
```
Single test file:
```bash
cd backend
uv run pytest -q tests/test_auth_routes.py
```
Single test case:
```bash
cd backend
uv run pytest -q tests/test_auth_routes.py::test_login_supports_username_or_email
```
Schema bootstrap check:
```bash
cd backend
uv run python -c "import asyncio; from app.db.init_db import ensure_database_schema; asyncio.run(ensure_database_schema()); print('schema ensured')"
```
Linting: no dedicated backend lint command configured.

### Frontend
Dev server:
```bash
cd frontend
npm run dev
```
All tests:
```bash
cd frontend
npm run test -- --run
```
Single test file:
```bash
cd frontend
npm run test -- --run src/stores/auth.test.ts
```
Single named test:
```bash
cd frontend
npm run test -- --run src/stores/auth.test.ts -t "stores token and user after login"
```
Build:
```bash
cd frontend
npm run build
```
Linting: no dedicated frontend lint command configured.

## 5) Backend Style Guidelines (Python)
### Imports
- Order: standard library, third-party, local `app.*`
- Prefer absolute imports from `app`
- Separate groups with one blank line

### Formatting and types
- Follow PEP 8 and 4-space indentation
- Add type hints for params/returns
- Use modern types (`User | None`, `dict[str, str]`)
- Keep functions cohesive and focused

### Naming
- `snake_case` for functions/variables/modules
- `PascalCase` for classes/exceptions
- `UPPER_SNAKE_CASE` for constants

### Error handling and logging
- Service layer raises domain errors (`UnauthorizedError`, `ConflictError`, etc.)
- Route layer maps domain errors to `HTTPException`
- Use `app/core/logging.py` helpers and structured `event=...` messages
- Never log plaintext passwords, full JWTs, or secrets

### Database patterns
- Use async SQLAlchemy sessions via `get_db_session()`
- Keep models in `app/models/`, bootstrap logic in `app/db/`
- PostgreSQL URL supports `database.schema` (e.g. `DreamBoDB.stockdb`)

## 6) Frontend Style Guidelines (TypeScript / Vue)
### General
- Use Vue 3 Composition API with `<script setup lang="ts">`
- Type API payloads and store state
- Keep components/views focused

### Imports and formatting
- External/framework imports first, local imports second
- Follow existing style: single quotes, no trailing semicolons
- Prefer `const` unless mutation is required

### Naming
- `camelCase` for variables/functions
- `PascalCase` for component/view files (`LoginView.vue`)
- Pinia stores named `useXStore`
- Route names lowercase (`home`, `login`, `profile`)

### State/API patterns
- Keep auth state in `src/stores/auth.ts`
- Keep wrappers in `src/api/`
- Throw typed `ApiError` with status codes
- Persist only required tokens

### Routing and guards
- Use route meta (`requiresAuth`, `guestOnly`)
- Protect routes with global `beforeEach`
- Preserve redirect query when bouncing to login
- After login, redirect to `query.redirect` or `/`

### UI consistency
- Preserve Neo Terminal design tokens (`--terminal-*`)
- Keep login/register/profile visual language aligned
- Use IBM Plex Sans + IBM Plex Mono pairing
- For new frontend pages/features, add appropriate motion/transition effects when they improve clarity and perceived quality

## 6.1) 中文注释规范（关键流程）
- 所有新增或修改的"关键流程"代码必须补充中文注释，至少覆盖：
  - 鉴权与安全边界（登录态、token、验证码、风控）
  - 关键业务分支（成功/失败/回滚/降级）
  - 易误用的状态流转与副作用（缓存、倒计时、重试、会话清理）
- 注释应解释"为什么这样做"和"边界条件"，避免逐行翻译代码。
- 优先在函数入口、关键分支、关键状态变更处添加注释；保持简洁。
- 禁止无信息量注释（如“设置变量”“调用接口”）。
- 代码评审与交付前需自查：本次功能点涉及的关键过程是否已补齐中文注释。

## 7) Testing Guidelines
- Follow TDD: failing test first, then minimal implementation
- Backend tests should stay isolated/deterministic
- Frontend tests should stub fetch (`vi.stubGlobal('fetch', ...)`)
- Reset stubs between tests (`vi.unstubAllGlobals()`)
- Prefer one behavior per test case

## 8) Secrets and Safety
- Never commit secrets or real credentials
- Keep runtime secrets in local `.env` files
- Treat SMTP/API/db credentials as sensitive
- Keep errors/logs sanitized

## 9) Agent Completion Checklist
- Run relevant tests before claiming completion
- If behavior changed, run build/start validation
- Update `README.md` when commands/behavior change
- Update `PROGRESS.md` for meaningful milestones
- Keep changes aligned with current architecture and naming
