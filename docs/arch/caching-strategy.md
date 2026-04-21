# Caching Architecture

Multi-layer caching strategy used throughout LiteLLM for API keys, rate limits, LLM responses, and embeddings.

## Caching Layers

LiteLLM uses a **three-tier caching strategy**:

```
┌─────────────────────┐
│ Tier 1: In-Memory   │ ← Process-local, <1ms access
│ (LRU + TTL)         │
└─────────────────────┘
         ↓ (cache miss)
┌─────────────────────┐
│ Tier 2: Redis       │ ← Shared across processes, ~1ms access
│ (DualCache wrapper) │
└─────────────────────┘
         ↓ (cache miss)
┌─────────────────────┐
│ Tier 3: Database    │ ← Persistent, 10-50ms access
│ (PostgreSQL/SQLite) │
└─────────────────────┘
```

## Cache Types

### 1. API Key Cache (Proxy)

**What**: API key metadata (spend limits, team, permissions, etc.)

**File**: `proxy/utils.py` (`InternalUsageCache`)

**Implementation**:
- In-memory: Dictionary of `{key_id: KeyMetadata}` with TTL
- Redis: Serialized metadata with 24-hour expiration
- Database: PostgreSQL `litellm_verification_token` table

**Invalidation**: Explicit invalidation on key update, TTL-based expiration

**Key Code**:
```python
InternalUsageCache.get_or_query(key_id)
  → Check in-memory
  → Check Redis
  → Query PostgreSQL
  → Update both caches
```

### 2. Rate Limit Counters (Redis only)

**What**: TPM/RPM counts, budget deductions

**File**: `proxy/hooks/parallel_request_limiter_v3.py`

**Implementation**:
- Redis only (no in-memory layer, needs to be shared across processes)
- Per-key, per-user, per-team counters
- Sliding window with second-level granularity

**Key Code**:
```python
Redis.INCR(f"rate_limit_key:{key_id}:{timestamp_bucket}")
Redis.EXPIRE(...)  # Auto-cleanup after window
```

**Invalidation**: Automatic expiration (sliding window)

### 3. LLM Response Cache (SDK)

**What**: Cached LLM completions (identical requests return cached response)

**File**: `caching/caching_handler.py` + `caching/caching.py`

**Implementation**:
- In-memory: `LRUCache` for single-process testing
- Redis: `RedisCache` for production
- S3: `S3Cache` for long-term archival
- PostgreSQL: `PostgreSQLCache`

**Cache Key**: Hash of `(model, messages, temperature, top_p, ...)`

**TTL**: Configurable per request (default: 24 hours)

**Example**:
```python
litellm.completion(
    model="gpt-4",
    messages=[...],
    caching={"type": "redis", "ttl": 3600}
)
```

**Invalidation**: TTL-based, explicit via API, or `cache=False` flag

### 4. Embedding Cache (SDK)

**What**: Cached embedding vectors (same text → same vector)

**File**: `caching/caching_handler.py`

**Implementation**: Same multi-tier as response cache

**Cache Key**: Hash of `(model, text, dimensions)`

## DualCache Implementation

`caching/dual_cache.py` provides a unified interface for in-memory + Redis:

```python
class DualCache:
    def __init__(self, in_memory_cache: InMemoryCache, redis_cache: RedisCache):
        pass
    
    async def get_or_set(self, key: str, fetch_fn):
        # Check in-memory first
        value = self.in_memory_cache.get(key)
        if value is not None:
            return value
        
        # Check Redis
        value = await self.redis_cache.get(key)
        if value is not None:
            self.in_memory_cache.set(key, value)  # Populate in-memory
            return value
        
        # Cache miss: fetch from source
        value = await fetch_fn()
        await self.redis_cache.set(key, value)
        self.in_memory_cache.set(key, value)
        return value
```

## Cache Backends

### Redis Backend

**File**: `caching/redis_cache.py`

**Features**:
- TTL support (auto-expiration)
- Serialization (JSON, pickle)
- Keyspace notifications for invalidation

**Performance**: ~1ms per operation

**Deployment**: Required for production multi-process setups

### In-Memory Backend

**File**: `caching/in_memory_cache.py`

**Features**:
- LRU eviction when size exceeded
- TTL-based expiration
- No network latency

**Performance**: <0.1ms per operation

**Limitation**: Not shared across processes; lost on restart

### S3 Backend

**File**: `caching/s3_cache.py`

**Use Case**: Long-term archival of responses (e.g., for compliance)

**Performance**: 50-500ms per operation (high latency, not recommended for real-time)

### PostgreSQL Backend

**File**: `caching/sql_cache.py`

**Use Case**: Simple deployments without Redis, or audit trail requirements

**Performance**: 10-50ms per operation

## Cache Size Management

### In-Memory LRU Eviction

```python
in_memory_cache = InMemoryCache(
    max_size_MB=100,  # Evict oldest when exceeded
    ttl_seconds=3600
)
```

### Redis Limits

Redis memory is managed via:
- TTL-based expiration (key-level)
- Eviction policy in Redis config (`maxmemory-policy`)

### PostgreSQL Cleanup

Old cache entries are cleaned up via:
- Manual cronjob (recommended)
- Application-level cleanup (batch delete)

## Cache Hit Rates

Monitor cache effectiveness:

**API Key Cache**: Usually >95% hit rate (keys reused frequently)

**Response Cache**: 10-50% hit rate (depends on query diversity)

**Rate Limit Cache**: 100% hit rate in cache (always in Redis)

## Invalidation Strategies

### Time-Based (TTL)
Most caches use TTL expiration. Default: 24 hours for responses, 1 hour for keys.

### Event-Based
- API key updated → Invalidate key cache
- Budget updated → Invalidate rate limit counters
- Response cache disabled → Skip cache

### Explicit
```python
litellm.cache.delete(key)
litellm.cache.clear()
```

## Cache Stampede Prevention

When many processes miss the same cache key simultaneously:

**Solution**: Use Redis `SET ... NX EX` pattern for distributed locking:

```python
# Try to acquire lock
if redis.set(f"lock:{key}", "1", ex=5, nx=True):
    # We got the lock, fetch data
    value = await fetch_data()
    redis.set(key, value)
else:
    # Another process is fetching, wait for result
    value = await redis.get(key, timeout=5)
```

## Security Considerations

### Token Leakage
- In-memory cache is per-process; don't share memory between users
- Redis is shared; use separate Redis instances for isolated environments

### Cache Poisoning
- Validate data before caching
- Use HMAC signatures for long-lived cached data

### PII in Logs
- Don't cache personally identifiable information in plain text
- Use Redis ACLs to restrict access to sensitive cache keys

