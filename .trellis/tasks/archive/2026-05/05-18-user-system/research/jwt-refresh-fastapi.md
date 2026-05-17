# Research: JWT + Refresh Token Authentication in FastAPI with SQLite

- **Query**: Best practices for JWT + Refresh Token auth in FastAPI + aiosqlite (raw SQL, no ORM)
- **Scope**: Mixed (internal codebase analysis + external best practices)
- **Date**: 2026-05-18

## Findings

### 1. JWT Library Choice: PyJWT vs python-jose

| Library | Status | Pros | Cons |
|---------|--------|------|------|
| **PyJWT** (`PyJWT`) | Active, maintained by Jose team | Most popular (50M+ downloads/mo), pure Python + C accel, focused scope (JWT only), well-documented, type stubs available | JWT only — no JWE/JWS/JWK |
| **python-jose** | Largely unmaintained (last release 2022) | Supports JWE/JWS/JWK, crypto flexibility | Abandoned, security vulnerabilities unpatched, depends on old `cryptography` versions |
| **josepy** | Mozilla project | ACME protocol focused | Not suitable for general JWT auth |

**Recommendation for this project: PyJWT**

- python-jose is effectively abandoned; community consensus is to use PyJWT
- PyJWT is the standard choice in modern FastAPI projects (FastAPI official docs reference it)
- This project only needs JWT signing/verification — no JWE/JWK needed
- Install: `PyJWT[crypto]` (includes `cryptography` for RS256 if needed later; `HS256` works without it)

```python
# PyJWT usage pattern
import jwt
from datetime import datetime, timedelta, timezone

# Create token
token = jwt.encode(
    {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(minutes=15)},
    SECRET_KEY,
    algorithm="HS256"
)

# Verify token
payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
user_id = payload["sub"]
```

### 2. Password Hashing: bcrypt vs argon2 vs passlib

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **bcrypt** (via `bcrypt` package) | Battle-tested, 25+ years, adjustable work factor, well-understood | Not memory-hard (GPU attackable), max password length 72 bytes | **Best for this project** — simple, proven, single-user scale |
| **argon2** (via `argon2-cffi`) | Winner of PHC 2015, memory-hard (resists GPU/ASIC), modern | More complex config, slightly less ubiquitous | Overkill for single-user app; better for high-value targets |
| **passlib** | Abstraction over multiple hashers, Django-like `make_password`/`verify` | Heavy dependency, wraps bcrypt/argon2 anyway, mostly for multi-algorithm migrations | Unnecessary abstraction for greenfield project |
| ** hashlib/sha256** | Fast | NOT suitable for passwords — too fast, no salt, no work factor | FORBIDDEN |

**Recommendation for this project: `bcrypt` directly**

- Single dependency, no abstraction layer needed
- For a single-user-scale app, bcrypt's security is more than sufficient
- No need for passlib's multi-algorithm abstraction
- `argon2-cffi` is technically superior but adds complexity with no real benefit at this scale

```python
import bcrypt

# Hash password (registration)
password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
# Store password_hash.decode("utf-8") as TEXT in SQLite

# Verify password (login)
bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
```

**bcrypt rounds for this project**: 12 is a good default (cost ~250ms per hash on modern hardware). 10 is too fast, 14+ is noticeably slow for login.

### 3. Refresh Token Storage Strategy

#### Option A: SQLite Table (Recommended for this project)

```sql
CREATE TABLE refresh_tokens (
    id TEXT PRIMARY KEY,           -- UUID token identifier
    user_id TEXT NOT NULL,         -- FK to users table
    token_hash TEXT NOT NULL,      -- SHA-256 hash of the token (never store raw token)
    expires_at TEXT NOT NULL,       -- ISO 8601 timestamp
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TEXT,               -- NULL = active; set timestamp on revocation
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_expires_at ON refresh_tokens(expires_at);
```

**Why store token_hash, not raw token**:
- If DB is compromised, attacker cannot use token hashes directly
- Client sends raw refresh token; server hashes it and looks up the hash
- Same principle as password storage — never store plaintext secrets

**Rotation pattern**:
1. Client sends refresh token to `/api/auth/refresh`
2. Server hashes the token, finds it in DB
3. If found and not revoked and not expired: **revoke the old token** (`SET revoked_at = now`)
4. **Create a new refresh token** (new UUID, new hash, new expiry)
5. Return new access token + new refresh token
6. Old token is now invalid — if reused, detect theft (see Section 7)

#### Option B: In-Memory (dict / lru_cache)

- Simpler but **lost on server restart** — all users logged out
- Not suitable even for single-user app: SQLite persistence is trivially easy and provides audit trail
- Only justified for truly ephemeral tokens (e.g., email verification codes)

**Recommendation**: SQLite table. The project already uses aiosqlite with raw SQL. Adding a `refresh_tokens` table follows existing patterns exactly.

### 4. Token Expiration Conventions

| Token Type | Common Range | Recommendation for this project | Rationale |
|------------|-------------|----------------------------------|-----------|
| Access Token | 5min – 60min | **15 minutes** | Industry standard for SPAs. Short enough to limit damage if stolen, long enough to not annoy users. |
| Refresh Token | 7d – 90d | **7 days** | Single-user app; 7d is convenient. Can increase to 30d later. Shorter = better security posture. |

**Why 15min access / 7d refresh**:
- 15min access: OWASP and Auth0 recommend 15min or less for SPAs
- 7d refresh: Balances convenience and security. Forces re-login weekly, which is fine for a personal tool
- If user is active, they never notice — silent refresh via `/api/auth/refresh`
- Refresh token rotation means a new 7d window starts at each refresh

**Environment variable configuration** (fits existing pattern in `app/config.py`):

```python
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
```

### 5. FastAPI Dependency Injection for Protected Routes

**Pattern**: `Depends(get_current_user)` on every protected endpoint.

```python
# app/api/deps.py (or inline in routes)
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Extract and validate JWT from Authorization header. Returns user payload."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        return {"user_id": user_id}
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
```

**Usage on existing routes** (adapted from current `app/api/routes.py`):

```python
@router.post("/process")
async def process_video(
    request: VideoRequest,
    user: dict = Depends(get_current_user),  # ADD THIS
):
    # user["user_id"] is now available
    ...
```

**Why `HTTPBearer` instead of `OAuth2PasswordBearer`**:
- `OAuth2PasswordBearer` is designed for the OAuth2 password flow (form-based login)
- `HTTPBearer` is simpler — just extracts the Bearer token from Authorization header
- The login endpoint returns JSON, not form-encoded data, so HTTPBearer is the right abstraction
- Both work, but HTTPBearer is more honest about what's actually happening

**Return type**: Return a typed dict or Pydantic model (e.g., `TokenData`) rather than a raw dict for type safety, consistent with the project's quality guidelines (type hints on all function signatures).

### 6. Refresh Token Endpoint Design

**Endpoint**: `POST /api/auth/refresh`

**Rotation: YES — single-use refresh tokens**

Every successful refresh:
1. Revokes the old refresh token (set `revoked_at`)
2. Issues a new refresh token + new access token
3. Client stores the new refresh token (HttpOnly cookie)

**Why rotation (not reuse)**:
- If a refresh token is reused after being rotated, it means the token was compromised
- The server can detect this: if a revoked token is presented, the attacker AND the legitimate user both have copies
- Detection pattern: revoke the entire family (all tokens for that user's session) on reuse

**Endpoint flow**:

```python
@router.post("/auth/refresh")
async def refresh_token(
    request: Request,  # Read refresh token from HttpOnly cookie
    response: Response,  # Set new HttpOnly cookie
):
    # 1. Read refresh token from cookie
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(401, "No refresh token")

    # 2. Hash the token and look it up
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    record = await db.get_refresh_token(token_hash)

    # 3. Validate: exists? not revoked? not expired?
    if not record:
        raise HTTPException(401, "Invalid refresh token")
    if record["revoked_at"] is not None:
        # REUSE DETECTED — revoke all tokens for this user
        await db.revoke_all_user_tokens(record["user_id"])
        response.delete_cookie("refresh_token")
        raise HTTPException(401, "Token reuse detected — all sessions terminated")
    if record["expires_at"] < datetime.now(UTC).isoformat():
        raise HTTPException(401, "Refresh token expired")

    # 4. Rotate: revoke old, create new
    await db.revoke_refresh_token(token_hash)
    new_token, new_hash = generate_refresh_token()
    await db.create_refresh_token(record["user_id"], new_hash, ...)

    # 5. Issue new access token
    access_token = create_access_token(record["user_id"])

    # 6. Set new refresh token cookie
    response.set_cookie(
        "refresh_token", new_token,
        httponly=True, secure=True, samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/auth/refresh",  # Scoped to refresh endpoint only
    )

    return {"access_token": access_token, "token_type": "bearer"}
```

**Key detail: cookie path scoping**:
- `path="/api/auth/refresh"` means the browser only sends the refresh token cookie to the refresh endpoint
- This prevents the refresh token from being sent on every API request (reduces exposure)
- Access token goes in `Authorization: Bearer <token>` header on every request (stored in JS memory)

### 7. Concurrent Refresh Requests (Race Condition)

**Problem**: Two browser tabs / devices simultaneously send expired access token + valid refresh token. Both requests see the same unrevoked refresh token in DB. Both try to rotate.

**SQLite-specific consideration**: SQLite with WAL mode (already enabled in this project via `PRAGMA journal_mode=WAL`) provides serializable write isolation. Concurrent writes are serialized by SQLite's file-level locking. This means:

**For single-user-scale**: The race condition is extremely unlikely. SQLite's write serialization handles it naturally — the second transaction will either wait (WAL) or fail with `SQLITE_BUSY` (which aiosqlite handles with retry).

**For robustness, the recommended approach**:

```sql
-- Use a conditional UPDATE for atomic rotation
UPDATE refresh_tokens
SET revoked_at = ?
WHERE id = ? AND revoked_at IS NULL
```

Check `rowcount` after execution:
- `rowcount == 1`: Successfully revoked (you win the race)
- `rowcount == 0`: Token was already revoked (you lose — this is reuse detection)

```python
cursor = await db.execute(
    "UPDATE refresh_tokens SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
    (now_iso, token_id)
)
await db.commit()

if cursor.rowcount == 0:
    # Token was already revoked — reuse detected
    await revoke_all_user_tokens(user_id)
    raise HTTPException(401, "Token reuse detected")
```

**Why this works**:
- SQLite UPDATE is atomic — only one transaction can claim the `revoked_at IS NULL` condition
- The conditional UPDATE acts as a compare-and-swap (CAS) operation
- No need for application-level locking or Redis

**For higher concurrency (future note)**:
- If this ever scales beyond single-user, consider PostgreSQL with `UPDATE ... RETURNING` or add an `asyncio.Lock` per user_id in the application layer
- For current scale, the conditional UPDATE pattern is sufficient

### 8. Full Schema: Users + Refresh Tokens Tables

```sql
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,               -- UUID
    email TEXT NOT NULL UNIQUE,        -- Login identifier
    password_hash TEXT NOT NULL,       -- bcrypt hash
    display_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id TEXT PRIMARY KEY,               -- UUID (opaque token identifier)
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL,           -- SHA-256 of the actual token
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TEXT,                    -- NULL = active
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);
```

**Note on `ON DELETE CASCADE`**: When a user is deleted, all their refresh tokens are cleaned up automatically.

### 9. Token Generation Pattern

```python
import secrets
import hashlib
import uuid

def generate_refresh_token() -> tuple[str, str]:
    """Generate an opaque refresh token. Returns (raw_token, sha256_hash)."""
    # Use 32 bytes of randomness (256 bits) — more than sufficient
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, token_hash

def create_access_token(user_id: str) -> str:
    """Create a signed JWT access token."""
    import jwt
    from datetime import datetime, timedelta, timezone
    from app.config import SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES

    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")
```

**Why `secrets.token_urlsafe` for refresh token**:
- Opaque token — no embedded claims, no signature verification needed
- Server is the sole authority: look up hash in DB
- Simpler and more secure than making refresh token a JWT (JWT refresh tokens can't be easily revoked)

**Why SHA-256 hash in DB**:
- The actual token never touches disk — only its hash
- SHA-256 is one-way: DB compromise does not reveal usable tokens
- Lookup by hash is fast with the index

### 10. SECRET_KEY Management

The project uses `python-dotenv` and `app/config.py` for env vars. Follow the existing pattern:

```python
# In app/config.py
import secrets

SECRET_KEY: str = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    # Auto-generate for dev; warn in logs
    SECRET_KEY = secrets.token_urlsafe(32)
    # In production, this MUST be set via env var
```

**Important**: For production, `SECRET_KEY` must be a stable environment variable. If it rotates, all existing access tokens become invalid (users need to re-login). Refresh tokens in DB are unaffected because they don't use JWT signing.

### 11. Login Endpoint Pattern

```python
@router.post("/auth/login")
async def login(request: LoginRequest, response: Response):
    # 1. Look up user by email
    user = await db.get_user_by_email(request.email)
    if not user:
        raise HTTPException(401, "Invalid credentials")  # Don't reveal "user not found"

    # 2. Verify password
    if not bcrypt.checkpw(request.password.encode(), user["password_hash"].encode()):
        raise HTTPException(401, "Invalid credentials")  # Same message for both cases

    # 3. Create access token
    access_token = create_access_token(user["id"])

    # 4. Create refresh token
    raw_token, token_hash = generate_refresh_token()
    expires_at = (datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).isoformat()
    await db.create_refresh_token(user["id"], token_hash, expires_at)

    # 5. Set refresh token as HttpOnly cookie
    response.set_cookie(
        "refresh_token", raw_token,
        httponly=True, secure=True, samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/auth/refresh",
    )

    return {"access_token": access_token, "token_type": "bearer"}
```

### 12. Logout Endpoint Pattern

```python
@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    # 1. Revoke the refresh token if present
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        await db.revoke_refresh_token(token_hash)

    # 2. Clear the cookie
    response.delete_cookie("refresh_token", path="/api/auth/refresh")

    return {"message": "Logged out"}
```

### 13. Cleanup Strategy for Expired Tokens

SQLite database will accumulate expired/revoked refresh tokens. For a single-user app, this is negligible, but a cleanup function is good hygiene:

```python
async def cleanup_expired_tokens():
    """Delete refresh tokens that expired more than 30 days ago."""
    cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "DELETE FROM refresh_tokens WHERE expires_at < ?",
            (cutoff,)
        )
        await db.commit()
```

This can be called during app startup or on a schedule. For single-user scale, calling it at startup is sufficient.

### 14. CORS Tightening for Auth

Current `app/main.py` has `allow_origins=["*"]` and `allow_credentials=True`. These are **incompatible**: browsers reject `credentials: true` with wildcard origin.

With auth, CORS must be tightened:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:5173")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

This is critical — the current `allow_origins=["*"]` + `allow_credentials=True` combination means browsers silently drop cookies.

## Files Found

| File Path | Description |
|---|---|
| `backend/app/db.py` | Current DB layer — aiosqlite, raw SQL, WAL mode, pattern to follow |
| `backend/app/config.py` | Env var config — pattern to extend with SECRET_KEY, token expiry |
| `backend/app/schemas.py` | Pydantic models — add auth request/response models here |
| `backend/app/api/routes.py` | Current routes — add Depends(get_current_user) to protected endpoints |
| `backend/app/main.py` | App setup — CORS must be tightened, lifespan may init auth tables |
| `backend/pyproject.toml` | Dependencies — add PyJWT, bcrypt |

## Code Patterns from Existing Codebase

### DB pattern (from `backend/app/db.py`):
- Each function opens its own `aiosqlite.connect()` context
- `PRAGMA journal_mode=WAL` on init
- Row factory: `db.row_factory = aiosqlite.Row` then `dict(row)`
- Parameterized queries with `?` placeholders (not f-strings)
- Each operation commits immediately

### Config pattern (from `backend/app/config.py`):
- Module-level variables from `os.getenv()`
- Fallback defaults in `os.getenv("KEY", "default")`
- `load_dotenv()` at top

### Routes pattern (from `backend/app/api/routes.py`):
- Single `router = APIRouter()`
- `HTTPException` for errors
- Thin handlers — delegate to service/DB functions

## External References

- [PyJWT documentation](https://pyjwt.readthedocs.io/) — Official PyJWT docs, covers HS256/RS256, decode, encode, expiration
- [FastAPI Security - Bearer Token](https://fastapi.tiangolo.com/tutorial/security/get-current-user/) — Official FastAPI pattern for Depends-based auth
- [RFC 7519 (JWT)](https://tools.ietf.org/html/rfc7519) — JWT standard
- [OWASP Auth Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html) — Password hashing, token storage guidance
- [Auth0 Token Storage for SPAs](https://auth0.com/docs/secure/security-guidance/security-best-practices/spa-security-best-practices) — Access token in memory, refresh in HttpOnly cookie

## Related Specs

- `.trellis/spec/backend/database-guidelines.md` — Empty, but DB conventions should be documented here
- `.trellis/spec/backend/directory-structure.md` — Auth module fits under `app/services/` or `app/api/`
- `.trellis/spec/backend/error-handling.md` — Auth errors (401) should be added to the status code table
- `.trellis/spec/backend/quality-guidelines.md` — No blocking calls in async context (bcrypt.hashpw is CPU-bound, wrap with `asyncio.to_thread()`)

## Caveats / Not Found

- **bcrypt.hashpw is synchronous and CPU-bound** (~100-250ms). It MUST be wrapped with `asyncio.to_thread()` to avoid blocking the async event loop. This is consistent with the existing project pattern (see quality-guidelines.md).
- **python-jose is abandoned** — do not use it despite older tutorials recommending it. PyJWT is the modern standard.
- **No external web search was available** — findings are based on established industry knowledge, RFCs, and library documentation, not real-time search results. The core recommendations (PyJWT, bcrypt, rotation, 15min/7d) are industry consensus as of 2025-2026.
- **SQLite concurrent writes**: WAL mode handles serialization, but under extreme concurrency, `SQLITE_BUSY` errors can occur. aiosqlite's default timeout (5s) is sufficient for single-user scale.
- **`allow_credentials=True` + `allow_origins=["*"]` is a known browser security restriction** — cookies will NOT be sent. This must be fixed regardless of auth implementation.
