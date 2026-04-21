# Cost Attribution Architecture

How LiteLLM calculates, tracks, and logs usage costs across all providers.

## Overview

LiteLLM tracks costs at multiple levels:
1. **Real-time calculation** — Cost computed immediately when response arrives
2. **Queued persistence** — Spend written to Redis queue (fast, async)
3. **Batch persistence** — Redis queue flushed to PostgreSQL periodically (60s interval)
4. **Reporting** — Team/user dashboards query PostgreSQL spend logs

## Cost Calculation Flow

```
LLM Response (includes token counts)
    ↓
litellm_logging.py: update_response_metadata()
    ↓
cost_calculator.py: completion_cost()
    ├─ model_prices_and_context_window.json (lookup provider price per 1k tokens)
    ├─ prompt_tokens × (prompt_price_per_1k / 1000)
    ├─ completion_tokens × (completion_price_per_1k / 1000)
    └─ return total_cost
    ↓
response._hidden_params["response_cost"] = cost
    ↓
Return response with cost metadata
```

## File Locations

| Component | File | Responsibility |
|-----------|------|-----------------|
| **Cost Calculation** | `cost_calculator.py` | Compute USD cost from token counts |
| **Logging Framework** | `litellm_logging.py` | Register callbacks and trigger async logging |
| **Response Metadata** | `llm_response_utils/response_metadata.py` | Extract/update cost in response object |
| **Proxy Cost Callback** | `proxy/hooks/proxy_track_cost_callback.py` | Queue cost to Redis (async) |
| **Spend Writer** | `proxy/db/db_spend_update_writer.py` | Batch write Redis queue to PostgreSQL |
| **Price Data** | `model_prices_and_context_window.json` | Provider prices per 1k tokens |
| **Spend Logs Schema** | `proxy/schema.prisma` → `LiteLLM_SpendLogs` | PostgreSQL table |

## Synchronous Path (In Request)

Cost is calculated **before** response returned to client:

1. `litellm.acompletion()` completes and returns `ModelResponse`
2. `main.py` wrapper calls `update_response_metadata(response, cost_key=True)`
3. `litellm_logging.py` calls `completion_cost(model, completion_tokens, prompt_tokens)`
4. `cost_calculator.py` looks up prices from JSON, multiplies by tokens, sums to USD
5. Cost stored in `response._hidden_params["response_cost"]`
6. Proxy extracts cost and adds to response header: `x-litellm-response-cost: 0.00456`

**Timing**: ~1-5ms (JSON lookup + arithmetic)

## Asynchronous Path (After Request)

Spend is **queued** immediately, **persisted** periodically:

```
Request completes
    ↓
proxy/common_request_processing.py
    Extract cost from hidden_params
    ↓
logging_obj.async_success_handler()
    (triggered after response sent to client)
    ↓
_ProxyDBLogger.async_log_success_event()
    ↓
DBSpendUpdateWriter.update_database()
    ├─ Queue to Redis: SET spend_updates:{key_id} += amount
    ├─ Update budget counters
    └─ Update rate limit TPM
    ↓
(Every 60 seconds, background job)
    
update_spend background job
    ├─ Read Redis queue: SMEMBERS spend_updates:*
    ├─ Aggregate by (key_id, user_id, team_id, model, ...)
    ├─ INSERT INTO litellm_spend_logs (batch of ~1000 rows)
    ├─ DELETE Redis queue entries
    └─ Repeat
```

## Why Async Queuing?

**Problem**: Writing to PostgreSQL for every request would be slow (10-50ms per write).

**Solution**: Queue to Redis (0.1ms), batch write every 60s (~1000 entries per write).

**Trade-off**: Spend appears in dashboard with ~60s delay, but client response is fast.

## Data Model

### Redis Queue
```
Key: spend_updates:{key_id}
Value: Aggregated spend since last batch write
Expires: Never (persisted to PostgreSQL)
```

### PostgreSQL (litellm_spend_logs)
```sql
CREATE TABLE litellm_spend_logs (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMP,
    key_id UUID,
    user_id UUID,
    team_id UUID,
    model VARCHAR,
    provider VARCHAR,
    completion_tokens INT,
    prompt_tokens INT,
    total_tokens INT,
    spend FLOAT,  -- USD
    request_id VARCHAR,
    response_time FLOAT,
    ...
);

CREATE INDEX ON litellm_spend_logs (key_id, timestamp);
CREATE INDEX ON litellm_spend_logs (user_id, timestamp);
CREATE INDEX ON litellm_spend_logs (team_id, timestamp);
```

## Rate Limiting Integration

Cost is also used for **budget enforcement**:

```
Request arrives
    ↓
Check budget (Redis): budget_remaining >= (estimated_tokens × avg_price)
    ↓
If over budget: reject with 429
    ↓
If OK: proceed with request
    ↓
After response: decrement budget by actual cost
```

## Multi-Provider Cost Tracking

Each provider has different prices (stored in `model_prices_and_context_window.json`):

| Provider | Prompt Price | Completion Price |
|----------|--------------|------------------|
| OpenAI (GPT-4) | $0.03/1k | $0.06/1k |
| Anthropic (Claude 3) | $0.003/1k | $0.015/1k |
| Google (Gemini) | $0.0001/1k | $0.0003/1k |

LiteLLM looks up prices by `(model, provider)` tuple and calculates accordingly.

## Known Limitations

1. **Custom models**: If model not in `model_prices_and_context_window.json`, cost is unknown (logged as $0.00)
2. **Token counting**: Uses provider-reported token counts (not always accurate)
3. **Prompt caching**: Some providers offer reduced rates for cached tokens (not yet tracked separately)

## Admin APIs for Cost Tracking

### Query Spend by Key
```python
GET /admin/spend?key_id={key_id}&start_date={iso_date}&end_date={iso_date}
```

### Query Spend by User
```python
GET /admin/spend/user?user_id={user_id}&start_date={iso_date}&end_date={iso_date}
```

### Query Spend by Team
```python
GET /admin/spend/team?team_id={team_id}&start_date={iso_date}&end_date={iso_date}
```

