# Refresh Token Global Revoke Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure all existing refresh tokens of a user are invalidated immediately after password change or password reset.

**Architecture:** Extend the token store with a per-user refresh-token index (`auth:user_refresh:{user_id}`) while preserving existing `jti -> user_id` validation (`auth:refresh:{jti}`). Revoke-all is implemented as an atomic Redis pipeline that deletes both the token keys and the index key. Password change/reset service flows trigger revoke-all after password hash is committed.

**Tech Stack:** FastAPI, SQLAlchemy async, redis-py asyncio, PyJWT, pytest

---

### Task 1: Add failing tests for global refresh invalidation

**Files:**
- Modify: `backend/tests/test_auth_routes.py`

**Step 1: Write failing test (change-password path)**

Add assertions in the existing auth integration flow:

```python
refresh_after_change_response = auth_client.post(
    "/api/auth/refresh",
    json={"refresh_token": login_payload["refresh_token"]},
)
assert refresh_after_change_response.status_code == 401
```

**Step 2: Write failing test (reset-password path)**

Add assertions in reset-password flow using the pre-reset login refresh token:

```python
refresh_after_reset_response = auth_client.post(
    "/api/auth/refresh",
    json={"refresh_token": before_reset_refresh_token},
)
assert refresh_after_reset_response.status_code == 401
```

**Step 3: Run tests and verify RED**

Run: `cd backend && uv run pytest -q tests/test_auth_routes.py -k "change_password_logout_flow or reset_password_flow"`

Expected: `FAIL` because old refresh token is still valid.

---

### Task 2: Extend token-store contract and in-memory test double

**Files:**
- Modify: `backend/app/cache/token_store.py`
- Modify: `backend/tests/test_auth_routes.py`

**Step 1: Add protocol method for user-level revoke-all**

```python
async def revoke_all_refresh_tokens_for_user(self, user_id: str) -> None: ...
```

**Step 2: Update in-memory token store implementation**

Track both maps:
- `jti -> user_id`
- `user_id -> set[jti]`

On single revoke, remove from both indexes.
On revoke-all, remove all indexed jtis for that user.

**Step 3: Re-run focused tests (still RED expected until service wiring)**

Run: `cd backend && uv run pytest -q tests/test_auth_routes.py -k "change_password_logout_flow or reset_password_flow"`

Expected: still `FAIL` on behavior assertions.

---

### Task 3: Implement Redis user-indexed refresh revoke-all

**Files:**
- Modify: `backend/app/cache/redis.py`

**Step 1: Update token issuance path to write both keys**

```python
async with self.client.pipeline(transaction=True) as pipe:
    await (
        pipe.set(f"auth:refresh:{jti}", user_id, ex=expires_seconds)
        .sadd(f"auth:user_refresh:{user_id}", jti)
        .execute()
    )
```

**Step 2: Update single-token revoke to maintain index consistency**

Implementation shape:
- Read `auth:refresh:{jti}` to resolve `user_id`
- Delete token key
- If user exists, `SREM` jti from user set

**Step 3: Add revoke-all method with atomic pipeline**

Implementation shape:
- `SMEMBERS auth:user_refresh:{user_id}`
- Build `auth:refresh:{jti}` keys
- In one pipeline: delete all token keys + delete user set key

**Step 4: Keep key naming aligned with P0 plan**

- `auth:refresh:{jti}`
- `auth:user_refresh:{user_id}`

---

### Task 4: Wire password security events to revoke-all

**Files:**
- Modify: `backend/app/services/auth_service.py`
- Modify: `backend/app/api/routes/auth.py`

**Step 1: Update service signatures**

```python
async def change_password(..., token_store: TokenStore) -> None
async def reset_password_by_email(..., token_store: TokenStore) -> None
```

**Step 2: Trigger global revoke after password commit**

Call:

```python
await token_store.revoke_all_refresh_tokens_for_user(user.id)
```

**Step 3: Update route callsites to pass dependency-injected token_store**

Apply to:
- `POST /api/auth/change-password`
- `POST /api/auth/reset-password`

**Step 4: Add/adjust Chinese comments on key security boundary**

Explain why post-password-event global revoke is required and what remains valid (access token until expiry).

---

### Task 5: Verify GREEN and regression coverage

**Files:**
- Test: `backend/tests/test_auth_routes.py`

**Step 1: Run targeted tests**

Run: `cd backend && uv run pytest -q tests/test_auth_routes.py -k "change_password_logout_flow or reset_password_flow"`

Expected: `PASS`.

**Step 2: Run full auth routes suite**

Run: `cd backend && uv run pytest -q tests/test_auth_routes.py`

Expected: all auth route tests `PASS`.

---

### Task 6: Documentation and milestone updates

**Files:**
- Modify: `README.md`
- Modify: `PROGRESS.md`

**Step 1: Document refresh invalidation behavior**

State explicitly: password change/reset revokes all existing refresh tokens for that user.

**Step 2: Add P0 milestone entry**

Record completion note in progress log.
