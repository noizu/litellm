# System Architecture Summary

Quick reference for LiteLLM's system design and key components.

## Core System

LiteLLM provides two complementary components:

1. **SDK** (`litellm/`) — Core LLM completion logic with 100+ provider support
2. **Proxy** (`litellm/proxy/`) — FastAPI server adding auth, rate limiting, cost tracking

Data flows: Client → Proxy (auth, rate limit, routing) → SDK (provider transformation) → LLM API

## Main Components

| Component | Purpose |
|-----------|---------|
| **Proxy Server** | FastAPI endpoint server, handles HTTP requests |
| **Router** | Load balancing, failover, deployment selection |
| **SDK** | Core completion logic, provider transformations |
| **Caching** | Multi-layer (in-memory, Redis, database) |
| **Authentication** | API keys, JWT, OAuth2 |
| **Cost Tracking** | Calculate, queue, and persist spend logs |
| **Background Jobs** | Async tasks (spend batching, budget reset, health checks) |
| **Providers** | 100+ LLM integrations with transformation layers |
| **Hooks** | Extension points for custom logic |

## Data Flow: Request

Client → Auth (Redis/PostgreSQL) → Rate Limit (Redis) → Router (strategy selection) → SDK (provider transform) → LLM API → Response transform → Cost calculation → Async logging → Client response

## Data Flow: Cost

Response tokens counted → Cost calculated (lookup from price table) → Stored in hidden params → Queued to Redis → Background job batches to PostgreSQL every 60 seconds

## Key Technologies

- **Framework**: FastAPI (async Python)
- **Database**: PostgreSQL (primary), SQLite (optional)
- **Caching**: Redis
- **ORM**: Prisma
- **Scheduler**: APScheduler
- **HTTP Client**: httpx
- **Observability**: OpenTelemetry, LangSmith, Datadog

## Caching Strategy

Three-tier model:
1. **In-Memory** — Process-local, <1ms
2. **Redis** — Shared, ~1ms
3. **Database** — Persistent, 10-50ms

Used for: API keys, rate limits, LLM responses, embeddings

## Routing Strategies

- **Least Busy** — Lowest concurrent request count
- **Weighted Shuffle** — Proportional to weight
- **Cost-Based** — Cheapest provider
- **Latency-Based** — Fastest response time
- **Failover** — Automatic fallback on provider failure

## Authentication Methods

- **API Keys** — Stored in PostgreSQL, cached in Redis
- **JWT** — OAuth2-compatible stateless tokens
- **OAuth2/OIDC** — External identity provider
- **Service-to-Service** — mTLS between proxies

## Cost Attribution

Synchronous (on request path):
1. Response tokens received
2. Cost calculated from model prices
3. Cost stored in response metadata
4. Cost included in response headers

Asynchronous (after response):
1. Cost queued to Redis
2. Background job batches queue every 60 seconds
3. Batched INSERT to PostgreSQL spend logs

## Background Jobs

| Job | Interval | Purpose |
|-----|----------|---------|
| update_spend | 60s | Flush Redis spend queue to PostgreSQL |
| reset_budget | 10-12m | Reset daily/monthly budgets |
| add_deployment | 10s | Sync new deployments from DB |
| health_check | continuous | Monitor provider health |
| cleanup_logs | daily | Delete old spend logs |

## Provider Architecture

Each provider has:
1. **Request transformation** — LiteLLM format → provider format
2. **Response transformation** — Provider format → OpenAI format
3. **Error mapping** — Provider errors → OpenAI errors
4. **Streaming support** — Transform streaming chunks

Supports 100+ providers: OpenAI, Anthropic, Google, Azure, AWS, Meta, Cohere, etc.

## Hooks & Callbacks

**Pre-call hooks** (synchronous, blocking):
- Budget validation
- Rate limit checks
- Permission validation

**Post-call callbacks** (asynchronous, non-blocking):
- LangSmith logging
- Datadog metrics
- OpenTelemetry traces
- Webhook notifications

## Rate Limiting

TPM (tokens per minute) and RPM (requests per minute) tracked per:
- API key
- User
- Team

Implemented with Redis sliding window counters

## Security

- Token scrubbing from logs
- HTTPS enforcement
- API key rotation
- Team/key-level access control
- Audit logging
- Rate limiting (DDoS protection)

## Performance

- Connection pooling per provider
- Response caching (avoid redundant calls)
- Async logging (non-blocking)
- Batched database writes (reduce load)
- In-memory caching (reduce latency)

