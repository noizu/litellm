# Background Jobs

Scheduled tasks that keep the proxy running smoothly without blocking request handling.

## Architecture

Background jobs are scheduled using **APScheduler** and run in separate threads/processes:

```
┌──────────────────────────┐
│ APScheduler              │
│ (initialized on startup) │
└───────────┬──────────────┘
            ↓
    ┌───────────────────┐
    │ Job 1: update_spend
    │ Job 2: reset_budget
    │ Job 3: add_deployment
    │ ... (8+ jobs)
    └───────────────────┘
            ↓
        Redis + PostgreSQL
```

**Initialization**: `proxy/proxy_server.py` → `ProxyStartupEvent.initialize_scheduled_background_jobs()`

## Job Registry

| Job | Interval | Priority | File | Purpose |
|-----|----------|----------|------|---------|
| **update_spend** | 60s | HIGH | `db/db_spend_update_writer.py` | Flush Redis spend queue to PostgreSQL |
| **reset_budget** | 10-12m | HIGH | `management_helpers/budget_reset_job.py` | Reset daily/monthly budgets |
| **add_deployment** | 10s | HIGH | `proxy_server.py` | Sync new deployments from DB |
| **_run_background_health_check** | continuous | MEDIUM | `proxy_server.py` | Monitor deployment health |
| **cleanup_old_spend_logs** | daily @ 2am | LOW | `management_helpers/spend_log_cleanup.py` | Delete spend logs >90 days old |
| **check_batch_cost** | 30min | MEDIUM | `management_helpers/check_batch_cost_job.py` | Calculate costs for batch jobs |
| **check_responses_cost** | 30min | MEDIUM | `management_helpers/check_responses_cost_job.py` | Calculate costs for responses API |
| **process_rotations** | 1hr | LOW | `management_helpers/key_rotation_manager.py` | Auto-rotate API keys |
| **send_weekly_spend_report** | weekly (Sunday) | LOW | `utils.py` (SlackAlerting) | Alert teams of weekly spend |
| **send_monthly_spend_report** | monthly (1st) | LOW | `utils.py` (SlackAlerting) | Alert teams of monthly spend |

## Critical Jobs

### 1. update_spend (60s interval)

**Purpose**: Persist cost data from Redis to PostgreSQL

**Flow**:
```
Redis queue: spend_updates:{key_id}
    ↓ (every 60s)
Read all queued spend
    ↓
Aggregate by (key_id, user_id, team_id, model, ...)
    ↓
INSERT INTO litellm_spend_logs (batch of ~1000 rows)
    ↓
DELETE queue entries from Redis
```

**Why 60s?**: Balance between freshness and database load. Avoid writing every request.

**Failure Handling**: If job fails, retries next iteration. Data stays in Redis.

### 2. reset_budget (10-12m interval)

**Purpose**: Reset daily/monthly budgets

**Flow**:
```
SELECT * FROM litellm_api_keys WHERE budget_reset_freq='daily' or 'monthly'
    ↓
Check if reset time passed
    ↓
UPDATE budget = max_budget
    ↓
Clear Redis counters for this key
```

**Why not on-request?**: Decouples budget enforcement from request latency.

### 3. add_deployment (10s interval)

**Purpose**: Detect new model deployments from proxy config

**Flow**:
```
SELECT * FROM litellm_deployment_table
    ↓
Compare with current router.model_list
    ↓
New deployments? Add to router
    ↓
Update router.cache
```

**Why 10s?**: Fast deployment detection without restart

### 4. _run_background_health_check (continuous)

**Purpose**: Monitor provider endpoint health

**Flow**:
```
For each deployment in router:
    ├─ Send test request (minimal payload)
    ├─ Track response time + success/failure
    ├─ If failure rate > threshold: mark unhealthy
    └─ Skip unhealthy deployments in routing
```

**Metrics Tracked**:
- Success rate
- Latency (p50, p99)
- Error types

## Low-Priority Jobs

### Cleanup Jobs

**cleanup_old_spend_logs**: Deletes spend logs older than 90 days

```sql
DELETE FROM litellm_spend_logs
WHERE created_at < NOW() - INTERVAL '90 days'
LIMIT 10000  -- Batch delete to avoid lock contention
```

**Why batch?**: Avoid long table locks during peak traffic.

### Cost Calculation Jobs

**check_batch_cost**: Calculate costs for OpenAI batch jobs (which complete asynchronously)

```
SELECT * FROM batch_jobs WHERE status='completed' AND cost IS NULL
    ↓
Query OpenAI API for token usage
    ↓
Calculate cost
    ↓
UPDATE batch_jobs SET cost=...
```

## Error Handling

Jobs catch exceptions and log failures:

```python
@scheduler.scheduled_job('interval', seconds=60)
async def update_spend():
    try:
        await db_spend_update_writer.update_database()
    except Exception as e:
        logger.error(f"update_spend failed: {e}")
        # Don't re-raise; let scheduler retry next interval
        # Data stays in Redis; next run will try again
```

**Behavior on Failure**:
- **Non-critical jobs** (reporting): Log and skip
- **Critical jobs** (spend): Retry next interval; alert if persistent failure
- **No retries within job**: Let scheduler retry on next cycle

## Job Isolation

Jobs run asynchronously to prevent blocking:

```python
# When proxy receives a request:
request → authenticate → rate limit → route → call SDK → return response
           (synchronous)

# Separately:
background job → update_spend → flush to PostgreSQL
(async, doesn't block request)
```

## Monitoring Jobs

### Metrics Exposed
- `job_execution_time_seconds` — How long each job takes
- `job_failure_rate` — Percentage of failed runs
- `job_last_run_timestamp` — When job last completed

### Logging
Each job logs:
- Start time
- Duration
- Success/failure
- Rows affected (if applicable)

### Alerts
On persistent failures:
```
update_spend failed 3 times in a row
→ Alert ops team
→ Manual check of Redis + PostgreSQL connectivity
```

## Configuration

Jobs can be configured via environment variables:

```python
# In proxy_server.py
{
    "update_spend_interval": int(os.getenv("UPDATE_SPEND_INTERVAL", 60)),  # seconds
    "reset_budget_interval": int(os.getenv("RESET_BUDGET_INTERVAL", 600)),  # seconds
    "add_deployment_interval": int(os.getenv("ADD_DEPLOYMENT_INTERVAL", 10)),  # seconds
}
```

## Scaling Considerations

### Multi-Proxy Deployments

When running multiple proxy instances:

**Problem**: Multiple instances running the same jobs (race conditions)

**Solution**: Use Redis locks for distributed coordination

```python
# Pseudo-code
@scheduler.scheduled_job(...)
async def job():
    lock_key = f"job_lock:{job_name}"
    
    if await redis.set(lock_key, "1", nx=True, ex=70):
        # Got lock, run job
        try:
            await do_job()
        finally:
            await redis.delete(lock_key)
    else:
        # Another instance has lock, skip
        pass
```

### Load on Database

Large spend updates can slow PostgreSQL:

**Optimization**: Batch inserts with `INSERT ... ON CONFLICT`

```python
INSERT INTO litellm_spend_logs (...) VALUES (...)
ON CONFLICT (key_id, timestamp) DO UPDATE SET spend = spend + EXCLUDED.spend
```

## Debugging Jobs

### Check Job Status
```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = ...
for job in scheduler.get_jobs():
    print(f"{job.name}: next_run={job.next_run_time}")
```

### View Job Logs
```bash
# Logs usually go to stderr or a log file
tail -f /var/log/litellm-proxy.log | grep "update_spend"
```

### Test Job Manually
```python
# Run job outside of scheduler
await update_spend()
```

