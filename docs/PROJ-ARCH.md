# System Architecture

LiteLLM is a unified interface for 100+ LLM providers with two complementary components: a **core SDK** for direct LLM calls and an **AI Gateway (Proxy)** that adds authentication, rate limiting, budgets, and observability.

## System Overview

```
Clients (OpenAI SDK, REST, etc.)
       ↓
┌──────────────────────────────────────┐
│  LiteLLM AI Gateway (Proxy)          │ ← Auth, rate limits, budgets, routing
│  litellm/proxy/                      │
└──────────────────────────────────────┘
       ↓
┌──────────────────────────────────────┐
│  LiteLLM SDK (litellm/)              │ ← Provider transformations, streaming
└──────────────────────────────────────┘
       ↓
  LLM Provider APIs (100+ vendors)
```

The **Gateway** adds enterprise features on top of the **SDK**. The **SDK** handles provider-specific protocol transformations and response normalization.

## Core Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **AI Gateway** | `litellm/proxy/` | FastAPI server with auth, rate limiting, cost tracking |
| **SDK** | `litellm/` | Core LLM completion logic, 100+ provider implementations |
| **Router** | `litellm/router.py` | Load balancing, fallback strategies, deployment management |
| **Caching** | `litellm/caching/` | Multi-backend caching (Redis, in-memory, S3) |
| **Integrations** | `litellm/integrations/` | Observability (LangSmith, Datadog, OpenTelemetry) |
| **Database** | `litellm/proxy/schema.prisma` | API keys, teams, users, spend logs (PostgreSQL/SQLite) |

## Request Flow

### Proxy (Gateway) Path

A client request flows through the Gateway like this:

→ *See [arch/proxy-request-flow.md](arch/proxy-request-flow.md) for detailed sequence diagrams*

1. **Client Request** → `/v1/chat/completions` endpoint
2. **Authentication** → API key verification (cached in Redis)
3. **Rate Limiting** → Check budgets and concurrent request limits (Redis)
4. **Routing** → Select best provider/model based on strategy
5. **SDK Call** → Invoke `litellm.acompletion()`
6. **Provider Transformation** → Convert request to provider-specific format
7. **HTTP Call** → Send to LLM provider API
8. **Response Transform** → Convert provider response to OpenAI format
9. **Cost Calculation** → Compute cost based on token usage
10. **Async Logging** → Queue spend update, trigger callbacks (non-blocking)
11. **Response** → Return to client with cost headers

### SDK (Core) Path

For direct SDK users, the flow is simpler:

→ *See [arch/sdk-request-flow.md](arch/sdk-request-flow.md) for details*

1. Call `litellm.completion()` or `litellm.acompletion()`
2. Resolve model → provider
3. Transform request to provider format
4. Make HTTP call
5. Transform response to OpenAI format
6. Handle streaming if requested
7. Return `ModelResponse` or stream

## Data Flow: Cost Attribution

Cost tracking is async to avoid slowing down responses:

→ *See [arch/cost-attribution.md](arch/cost-attribution.md) for detailed flow*

1. Response returns with token counts
2. Cost calculated via `completion_cost()` (token count × provider prices)
3. Cost stored in response metadata
4. Queued to Redis (not written to DB immediately)
5. Background job flushes batch updates every 60 seconds

## Infrastructure

### Caching Layers

```
┌─────────────────────────┐
│ In-Memory Cache         │  Fast, per-process
├─────────────────────────┤
│ Redis (DualCache)       │  Fast, shared across processes
├─────────────────────────┤
│ PostgreSQL / S3         │  Persistent storage
└─────────────────────────┘
```

→ *See [arch/caching-strategy.md](arch/caching-strategy.md) for cache backend details*

### Storage

- **PostgreSQL**: API keys, teams, users, spend logs (production)
- **SQLite**: Optional for simpler deployments
- **Redis**: Rate limits, API key cache, spend queue, LLM response cache

### Background Jobs

Scheduled tasks keep the system responsive:

→ *See [arch/background-jobs.md](arch/background-jobs.md) for full list*

| Job | Interval | Purpose |
|-----|----------|---------|
| `update_spend` | 60s | Batch write spend logs to PostgreSQL |
| `reset_budget` | 10-12m | Reset budgets for keys/users/teams |
| `add_deployment` | 10s | Sync model deployments from DB |
| `_run_background_health_check` | continuous | Monitor deployment health |

## Provider Integrations

LiteLLM supports 100+ LLM providers through a unified interface:

→ *See [arch/provider-architecture.md](arch/provider-architecture.md) for provider details*

Each provider has:
- **Transformation layer** (`llms/{provider}/chat/transformation.py`) — convert request/response format
- **HTTP handler** — standard HTTP client with provider-specific config
- **Error mapping** — normalize provider errors to OpenAI exceptions

Example providers: OpenAI, Anthropic, Google, Azure, AWS Bedrock, Cohere, Hugging Face, Meta Llama, and 90+ others.

## Key Design Decisions

### Request Async Logging
Cost calculation and database writes are decoupled from the response path. Callbacks happen asynchronously to minimize latency.

**Why**: Cost calculation requires token counting (synchronous), but database writes should not block responses.

→ *See [arch/cost-attribution.md](arch/cost-attribution.md) for details*

### Dual-Layer Caching (In-Memory + Redis)
Every cache operation checks in-memory first, then Redis, then database.

**Why**: In-memory cache is fast for a single process; Redis is fast for cross-process caching; DB is authoritative.

→ *See [arch/caching-strategy.md](arch/caching-strategy.md) for details*

### Router as a Separate System
Load balancing and fallback logic is decoupled from the proxy into `router.py`.

**Why**: Router is usable standalone (direct SDK users), and proxy just orchestrates router calls.

→ *See [arch/router-architecture.md](arch/router-architecture.md) for details*

## Authentication & Authorization

The proxy supports multiple auth methods:

→ *See [arch/authentication.md](arch/authentication.md) for full auth design*

- **API Keys** — Stored in PostgreSQL, cached in Redis
- **JWT** — Stateless tokens
- **OAuth2** — OIDC-compatible (external IdP)
- **Service-to-Service** — Internal routing between proxies

## Extensibility: Custom Hooks

The proxy provides hooks for custom logic:

→ *See [arch/hooks-and-callbacks.md](arch/hooks-and-callbacks.md) for hook design*

| Hook | Purpose |
|------|---------|
| `max_budget_limiter` | Enforce budget limits before routing |
| `parallel_request_limiter` | Rate limit concurrent requests per key/user |
| `cache_control_check` | Validate cache headers |
| `litellm_skills` | Inject LLM skills/actions |

Custom hooks implement `CustomLogger` interface and register in `PROXY_HOOKS`.

## Technology Stack

- **Framework**: FastAPI (async Python)
- **Database**: PostgreSQL (primary), SQLite (optional)
- **Caching**: Redis
- **ORM**: Prisma
- **Async Runtime**: asyncio + APScheduler (background jobs)
- **HTTP Client**: httpx (with custom connection pooling)
- **Observability**: OpenTelemetry, LangSmith, Datadog, New Relic

## Architecture References

For deeper dives into specific areas, see:

- [arch/proxy-request-flow.md](arch/proxy-request-flow.md) — Detailed proxy request sequence
- [arch/sdk-request-flow.md](arch/sdk-request-flow.md) — SDK request handling
- [arch/cost-attribution.md](arch/cost-attribution.md) — Cost calculation flow
- [arch/caching-strategy.md](arch/caching-strategy.md) — Caching architecture
- [arch/router-architecture.md](arch/router-architecture.md) — Router design
- [arch/provider-architecture.md](arch/provider-architecture.md) — Provider integration pattern
- [arch/authentication.md](arch/authentication.md) — Auth methods and design
- [arch/background-jobs.md](arch/background-jobs.md) — Scheduled tasks
- [arch/hooks-and-callbacks.md](arch/hooks-and-callbacks.md) — Extension points

---

**See also:** [../ARCHITECTURE.md](../ARCHITECTURE.md) for the original detailed architecture document.

