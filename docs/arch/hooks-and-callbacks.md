# Hooks and Callbacks

Extension points for custom logic in the proxy and SDK.

## Architecture

```
Request arrives
    ↓
Proxy hooks (proxy/hooks/)
    ├─ max_budget_limiter (before routing)
    ├─ parallel_request_limiter
    └─ cache_control_check
    ↓
Router (routing decision)
    ↓
SDK call (litellm.acompletion())
    ↓
Response received
    ↓
SDK callbacks (integrations/)
    ├─ LangSmith logger
    ├─ Datadog logger
    ├─ OpenTelemetry logger
    └─ Custom callbacks
    ↓
Proxy callbacks (proxy/hooks/)
    └─ Cost tracking callback
    ↓
Response returned
```

## Proxy Hooks

Proxy hooks run **before routing** and can modify requests or reject them.

**File**: `proxy/hooks/__init__.py` - Registry of all hooks

**Base Class**: `CustomLogger` (from `litellm_logging.py`)

### Hook Types

#### Pre-Call Hooks
Run **before** the request reaches the SDK:

```python
class CustomLogger(CustomObject):
    async def async_pre_call_hook(self, user, model, messages, kwargs):
        # Called before litellm.acompletion()
        # Can modify: messages, model, kwargs
        # Can reject: raise exception
        pass
```

**Hooks Registered**:
- `max_budget_limiter` — Enforce budget before request
- `parallel_request_limiter_v3` — Rate limit before request
- `cache_control_check` — Validate cache headers

#### Post-Call Hooks
Run **after** the response is received:

```python
async def async_log_success_event(self, response):
    # Called after response received
    # Can log, queue, or trigger async tasks
    pass
```

**Hooks Registered**:
- `_ProxyDBLogger` (in `proxy_track_cost_callback.py`) — Queue spend to Redis

#### Error Hooks
Run **when request fails**:

```python
async def async_log_failure_event(self, kwargs, response, error):
    # Called on error
    # Can log or alert
    pass
```

## Example: Custom Budget Hook

```python
# in proxy/hooks/

from litellm.litellm_logging import CustomLogger

class CustomBudgetHook(CustomLogger):
    def __init__(self, db_client, redis_client):
        self.db = db_client
        self.redis = redis_client
    
    async def async_pre_call_hook(self, user, model, messages, kwargs):
        """Check budget before allowing request"""
        # Get user budget
        budget_key = f"budget:{user}"
        remaining = await self.redis.get(budget_key)
        
        if not remaining or float(remaining) < 0.01:  # Less than 1 cent
            raise BudgetLimitExceeded(
                f"User {user} has no budget remaining"
            )
        
        # Log the check
        print(f"Budget check passed for {user}")
    
    async def async_log_success_event(self, response):
        """After response, update budget"""
        cost = response.get("_hidden_params", {}).get("response_cost", 0)
        user = response.get("user_id")
        
        # Decrement budget
        budget_key = f"budget:{user}"
        await self.redis.decrby(budget_key, cost)

# Register in proxy_server.py or hooks/__init__.py
PROXY_HOOKS = {
    "CustomBudgetHook": CustomBudgetHook
}
```

## SDK Callbacks (Integrations)

SDK callbacks run **asynchronously** after response and don't block the response.

**Location**: `litellm/integrations/`

**Base Class**: `CustomLogger`

### Supported Integrations

| Integration | File | Purpose |
|-------------|------|---------|
| **LangSmith** | `integrations/langsmith.py` | Trace LLM calls, debug, prompt management |
| **Datadog** | `integrations/datadog.py` | Metrics, logs, APM |
| **New Relic** | `integrations/newrelic.py` | Performance monitoring, errors |
| **OpenTelemetry** | `integrations/opentelemetry.py` | Standard observability |
| **Honeycomb** | `integrations/honeycomb.py` | Event tracing |
| **Slack** | `integrations/slack.py` | Alerts and notifications |
| **Custom Webhook** | `integrations/webhook.py` | Send data to custom endpoint |

### Example: LangSmith Integration

```python
# in integrations/langsmith.py

from litellm.litellm_logging import CustomLogger

class LangSmithLogger(CustomLogger):
    async def async_log_success_event(self, response, user, model, ...):
        """Log successful completion to LangSmith"""
        import langsmith
        
        # Create run
        run = langsmith.Run(
            name="litellm_completion",
            inputs={
                "model": model,
                "messages": messages,
            },
            outputs={
                "completion": response.choices[0].message.content,
            }
        )
        
        # Log to LangSmith API
        await langsmith.alog_run(run)
```

### Registering Custom Callback

```python
# In your application code

from litellm import Router
from my_callbacks import MyCustomLogger

router = Router(
    model_list=[...],
    callbacks=[MyCustomLogger()]  # Pass instance
)

# Now all completions will trigger MyCustomLogger hooks
response = await router.acompletion(...)
```

## Hook Execution Order

1. **Proxy pre-call hooks** (synchronous, blocking)
   - Check budgets, rate limits, permissions
   - Can reject request (raise exception)

2. **SDK call** (synchronous)
   - Call provider API
   - Get response

3. **SDK callbacks** (asynchronous, non-blocking)
   - Log to LangSmith, Datadog, etc.
   - Runs in background after response returned

4. **Proxy post-call hooks** (synchronous, but after response sent)
   - Queue spend to Redis
   - Update metrics

## Hook Configuration

### Environment Variables

```bash
# Enable specific integrations
LITELLM_LANGSMITH_API_KEY=...
LITELLM_DATADOG_API_KEY=...
LITELLM_OPENTELEMETRY_ENABLED=true

# Custom webhook
LITELLM_CUSTOM_LOGGER_WEBHOOK_URL=https://my-service/logs
```

### Config File

```yaml
# in proxy_server_config.yaml

callbacks:
  - type: "langsmith"
    api_key: "${LANGSMITH_API_KEY}"
  
  - type: "datadog"
    api_key: "${DATADOG_API_KEY}"
  
  - type: "custom"
    class: "my_module.MyLogger"
    init_params:
      endpoint: "https://my-service/logs"
```

## Error Handling in Hooks

**Pre-call hooks** can reject requests:

```python
async def async_pre_call_hook(self, user, model, messages, kwargs):
    if not self.is_user_allowed(user, model):
        raise PermissionDenied(f"User {user} cannot use {model}")
```

**Post-call hooks** should not raise (runs after response):

```python
async def async_log_success_event(self, response):
    try:
        await self.send_to_external_service(response)
    except Exception as e:
        # Log error but don't raise
        logger.error(f"Failed to log response: {e}")
```

## Performance Considerations

### Pre-Call Hooks (Synchronous)
- Runs on request path, blocks response
- Keep operations fast (<10ms)
- Use caching (Redis) to minimize DB queries

### Post-Call Hooks (Asynchronous)
- Runs after response, doesn't block
- Okay to do slower operations
- Still avoid blocking for too long (>1s)

### Example: Efficient Budget Check

❌ **Slow**: Query database every request
```python
async def async_pre_call_hook(self, ...):
    budget = await db.query("SELECT budget FROM users WHERE id=?", user)
    # 10-50ms latency!
```

✅ **Fast**: Check cache, fallback to database
```python
async def async_pre_call_hook(self, ...):
    budget = await self.cache.get_or_set(
        f"budget:{user}",
        lambda: db.query(...),
        ttl=3600  # 1 hour cache
    )
    # <1ms if cached, 10-50ms if miss
```

## Testing Hooks

### Unit Test

```python
import pytest
from my_hooks import CustomBudgetHook

@pytest.mark.asyncio
async def test_budget_limit():
    hook = CustomBudgetHook(db=mock_db, redis=mock_redis)
    
    # Simulate no budget
    await mock_redis.set("budget:user_1", "0")
    
    # Should raise
    with pytest.raises(BudgetLimitExceeded):
        await hook.async_pre_call_hook(
            user="user_1",
            model="gpt-4",
            messages=[...],
            kwargs={}
        )
```

### Integration Test

```python
@pytest.mark.asyncio
async def test_with_real_proxy():
    response = await router.acompletion(
        model="gpt-4",
        messages=[...],
        user="test_user"
    )
    
    # Check that hook was triggered
    # (e.g., cost was logged)
    assert response.get("_hidden_params", {}).get("response_cost")
```

## Common Hook Patterns

### Rate Limiting
```python
async def async_pre_call_hook(self, ...):
    if not await self.rate_limiter.allow(user):
        raise RateLimitExceeded()
```

### Audit Logging
```python
async def async_log_success_event(self, response):
    await self.audit_log.write({
        "timestamp": now(),
        "user": response.user,
        "model": response.model,
        "tokens": response.usage.total_tokens
    })
```

### Feature Gating
```python
async def async_pre_call_hook(self, ...):
    if model == "gpt-4" and not user.has_feature("gpt4"):
        raise ModelNotAllowed()
```

