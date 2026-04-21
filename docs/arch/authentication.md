# Authentication & Authorization

The proxy supports multiple authentication methods for API access and team/user isolation.

## Supported Auth Methods

### 1. API Keys

**Storage**: PostgreSQL `litellm_verification_token` table

**Flow**:
```
Client sends: Authorization: Bearer sk-1234567890
    ↓
Proxy validates: Check Redis cache, fallback to PostgreSQL
    ↓
Extract: user_id, team_id, budget, permissions
    ↓
Proceed with request
```

**Features**:
- Per-key budget limits (USD)
- Per-key rate limits (TPM, RPM)
- Per-key model allowlists
- Automatic key rotation support

**API**:
```python
POST /admin/api_keys
{
    "team_id": "team_123",
    "user_id": "user_456",
    "duration": "30d",
    "budget": 100,  # USD
    "model_whitelist": ["gpt-4", "gpt-3.5-turbo"]
}
→ Returns: {"key": "sk-..."}
```

### 2. JWT (JSON Web Tokens)

**Format**: OAuth2-compatible JWT

**Flow**:
```
Client sends: Authorization: Bearer eyJhbGc...
    ↓
Proxy validates: Signature + expiry
    ↓
Extract: Claims (user_id, team_id, permissions)
    ↓
Proceed
```

**Config** (`proxy_server.py`):
```python
# Environment variable
LITELLM_JWT_PUBLIC_KEY_URL="https://auth.example.com/.well-known/jwks.json"
# or
LITELLM_JWT_SECRET="your-secret-key"
```

**Claims**:
```json
{
    "sub": "user_123",
    "team_id": "team_456",
    "permissions": ["read", "write"],
    "budget": 100,
    "iat": 1234567890,
    "exp": 1234571490
}
```

### 3. OAuth2 / OIDC

**Flow**:
```
Client redirects to: /oauth/authorize
    ↓
Proxy redirects to: OIDC provider (e.g., Google, Azure AD)
    ↓
User authenticates
    ↓
Proxy receives authorization code
    ↓
Exchange code for ID token + refresh token
    ↓
Create session + return to client
```

**Config**:
```python
LITELLM_OAUTH_CLIENT_ID="..."
LITELLM_OAUTH_CLIENT_SECRET="..."
LITELLM_OAUTH_PROVIDER_URL="https://auth.example.com"
```

**Stored**: `litellm_user_session` table (access token, refresh token, user_id, team_id)

### 4. Service-to-Service

**Use**: Proxy-to-proxy communication or internal routing

**Method**: Mutual TLS (mTLS) or shared secret

**Config**:
```python
# In config.yaml
service_auth:
  method: "mTLS"
  cert_path: "/etc/certs/server.crt"
  key_path: "/etc/certs/server.key"
  ca_path: "/etc/certs/ca.crt"
```

## Authorization Model

Users belong to **teams**, which control access:

```
┌──────────────────┐
│ Team (team_123)  │
├──────────────────┤
│ ├─ user_1        │
│ ├─ user_2        │
│ ├─ API key_1     │
│ ├─ API key_2     │
│ ├─ Budget: $1000 │
│ └─ Models: gpt-4 │
└──────────────────┘
```

### Team-Level Controls

Each team has:
- **Budget** — Total USD allowed per month
- **Model allowlist** — Which models can be used
- **Rate limits** — TPM/RPM quotas
- **Members** — Which users can use this team

### Key-Level Controls

Each API key has:
- **Budget** — USD allowed before expiry
- **Model allowlist** — Subset of team allowlist
- **Rate limits** — Own TPM/RPM quotas
- **Expiry** — Optional expiration date
- **Permissions** — read, write, admin

## Access Control

### Model Access Control

1. **Team allowlist**: Team admin specifies `allowed_models`
2. **Key allowlist**: API key can further restrict models
3. **Request check**: `if model not in key.allowed_models → reject`

### Budget Enforcement

1. **Team budget**: Total monthly spend limit
2. **Key budget**: Per-key daily/monthly limit
3. **Request check**: `if remaining_budget < estimated_cost → reject`

### Endpoint Authorization

Some endpoints require additional permissions:

| Endpoint | Required Permission |
|----------|-------------------|
| `/v1/chat/completions` | read |
| `/admin/api_keys` | admin |
| `/admin/teams` | admin |
| `/admin/budgets` | admin |

## Rate Limiting

Each API key/user/team has separate limits:

### Per-Key Limits
```
TPM (tokens per minute): 100k
RPM (requests per minute): 1000
```

### Per-Team Limits
```
TPM (tokens per minute): 1M
RPM (requests per minute): 10k
```

**Implementation**: Sliding window counters in Redis

**Enforcement**: 429 Too Many Requests if exceeded

## Authentication Flow Diagram

```
┌─────────────────┐
│ Client Request  │
└────────┬────────┘
         ↓
┌────────────────────────────────┐
│ Extract Authorization Header   │
│ (Bearer token)                 │
└────────┬───────────────────────┘
         ↓
┌────────────────────────────────┐
│ Determine Auth Type            │
│ - API Key? JWT? OAuth?         │
└────────┬───────────────────────┘
         ↓
     ╔═══════════════════════╗
     ║ Validate Token        ║
     ║ (provider-specific)   ║
     ╚═════════┬═════════════╝
         ↓
┌────────────────────────────────┐
│ Extract Claims                 │
│ user_id, team_id, permissions  │
└────────┬───────────────────────┘
         ↓
┌────────────────────────────────┐
│ Check Cache (Redis)            │
│ Hit? Return metadata           │
│ Miss? Query PostgreSQL         │
│ Update Redis cache             │
└────────┬───────────────────────┘
         ↓
┌────────────────────────────────┐
│ Check Authorization            │
│ - Model in allowlist?          │
│ - Budget remaining?            │
│ - Rate limit OK?               │
└────────┬───────────────────────┘
         ↓
    ╔═══════════════════════╗
    ║ Proceed or Reject (4xx) ║
    ╚═══════════════════════╝
```

## Implementation Files

| Component | File | Purpose |
|-----------|------|---------|
| **Auth entry point** | `proxy/auth/user_api_key_auth.py` | Middleware that validates all requests |
| **API key validation** | `proxy/auth/api_key.py` | Lookup and validate API keys |
| **JWT validation** | `proxy/auth/jwt_handler.py` | Validate JWT signatures |
| **OAuth handling** | `proxy/oauth/` | OAuth2/OIDC flows |
| **Cache** | `proxy/utils.py` (InternalUsageCache) | In-memory + Redis cache |
| **Database models** | `proxy/schema.prisma` | Tables: users, teams, api_keys, sessions |

## Security Best Practices

1. **Never log tokens**: Scrub tokens from logs
2. **Use HTTPS only**: Enforce TLS in production
3. **Token rotation**: Require regular key rotation
4. **Budget guardrails**: Set team/key budgets conservatively
5. **Audit logging**: Log all auth attempts (success + failure)
6. **Rate limiting**: Use to prevent brute force
7. **API key scoping**: Use least-privilege (model allowlists)

## Admin APIs for Auth Management

### Create API Key
```bash
curl -X POST http://localhost:8000/admin/api_keys \
  -H "Authorization: Bearer ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "team_id": "team_123",
    "duration": "30d",
    "budget": 100,
    "model_whitelist": ["gpt-4"]
  }'
```

### List API Keys
```bash
curl http://localhost:8000/admin/api_keys/team/team_123 \
  -H "Authorization: Bearer ${ADMIN_KEY}"
```

### Update Key Budget
```bash
curl -X PUT http://localhost:8000/admin/api_keys/sk_123 \
  -H "Authorization: Bearer ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"budget": 200}'
```

### Revoke Key
```bash
curl -X DELETE http://localhost:8000/admin/api_keys/sk_123 \
  -H "Authorization: Bearer ${ADMIN_KEY}"
```

