# Router Architecture

The Router system handles load balancing, failover, and deployment management across multiple LLM providers and models.

## Purpose

The `Router` class decouples routing logic from the proxy, enabling:
- **Standalone usage**: Direct SDK users can use Router without proxy
- **Multi-model fallback**: Automatic failover across providers
- **Load balancing**: Distribute traffic across deployments
- **Cost optimization**: Route to cheapest provider
- **Latency optimization**: Route to fastest provider

## Core Components

```
┌────────────────────────────────┐
│ Router (router.py)             │
│ - Maintains deployments list   │
│ - Manages cache (DualCache)    │
│ - Applies routing strategy     │
└────────────────────────────────┘
        ↓
┌────────────────────────────────┐
│ Routing Strategies             │
│ (router_strategy/)             │
│ - Least busy first             │
│ - Weighted shuffle             │
│ - Cost-based                   │
│ - Latency-based                │
└────────────────────────────────┘
        ↓
┌────────────────────────────────┐
│ Deployment Config              │
│ (model_list from config.yaml)  │
│ - Provider name                │
│ - Model name                   │
│ - Weights                      │
│ - Priority                     │
└────────────────────────────────┘
```

## Router Configuration

### Programmatic API

```python
from litellm import Router

router = Router(
    model_list=[
        {
            "model_name": "gpt-4",
            "litellm_params": {
                "model": "gpt-4",
                "api_key": os.getenv("OPENAI_API_KEY")
            },
            "weight": 1.0,
            "priority": 0
        },
        {
            "model_name": "gpt-4",
            "litellm_params": {
                "model": "claude-3-opus",
                "api_key": os.getenv("ANTHROPIC_API_KEY")
            },
            "weight": 1.0,
            "priority": 1  # Fallback
        }
    ],
    routing_strategy="least-busy"
)

response = await router.acompletion(
    model="gpt-4",
    messages=[...]
)
```

### Config File (YAML)

```yaml
model_list:
  - model_name: gpt-4
    litellm_params:
      model: gpt-4
      api_key: ${OPENAI_API_KEY}
    weight: 1.0
    priority: 0
    
  - model_name: gpt-4
    litellm_params:
      model: claude-3-opus
      api_key: ${ANTHROPIC_API_KEY}
    weight: 1.0
    priority: 1  # Fallback to this if above fails

routing_strategy:
  strategy_name: least-busy
  min_availability_percentage: 80
  fallback_after_x_seconds: 5
```

## Routing Strategies

### Least Busy (`least_busy.py`)

Routes requests to the deployment with the **lowest current load**:

```python
# Track metrics per deployment
deployments_metrics = {
    "gpt-4-openai": {
        "current_requests": 5,
        "avg_latency": 150,  # ms
        "failure_rate": 0.01
    },
    "gpt-4-azure": {
        "current_requests": 2,  # ← Lower load
        "avg_latency": 200,
        "failure_rate": 0.02
    }
}

# Select deployment with lowest current_requests
```

**Use Case**: Minimize tail latency in high-concurrency scenarios

### Weighted Shuffle (`weighted_shuffling.py`)

Routes requests based on **weights**, randomized:

```python
# Config specifies weights
deployments = [
    {"name": "openai", "weight": 1.0},   # 50%
    {"name": "azure", "weight": 1.0},   # 50%
    {"name": "anthropic", "weight": 0.5}  # 25%
]

# Randomly select proportional to weight
# Over 100 requests: ~50 to OpenAI, ~50 to Azure, ~25 to Anthropic
```

**Use Case**: Distribute traffic proportionally; easier to control than dynamic strategies

### Cost-Based (`cost_based.py`)

Routes to the **cheapest** provider:

```python
# Route to provider with lowest cost
if gpt-4_openai_cost < gpt-4_azure_cost:
    route_to_openai()
else:
    route_to_azure()
```

**Use Case**: Minimize infrastructure costs while maintaining acceptable latency

### Latency-Based (`latency_based.py`)

Routes to the **fastest** provider (measured empirically):

```python
# Track latency per deployment
latencies = {
    "gpt-4-openai": 150,
    "gpt-4-azure": 200,
}

# Route to lowest latency
route_to(min(latencies, key=latencies.get))
```

**Use Case**: Optimize for user-facing latency

## Failover / Retry Logic

When a deployment fails, Router automatically **retries** with next priority:

```
Request → gpt-4-openai (primary)
         ↓ [Fails: timeout, 500 error, auth failure]
         → gpt-4-azure (priority=1)
         ↓ [Succeeds]
         ← Return response
```

**Failover Config**:
```yaml
routing_strategy:
  fallback_after_x_seconds: 5  # Give primary 5s before trying fallback
  min_availability_percentage: 80  # Skip deployment if >20% errors
```

## Deployment Management

Router maintains a list of **active deployments** that it selects from.

### Model Name Resolution

When you call `router.completion(model="gpt-4", ...)`:

1. Router looks up all deployments with `model_name == "gpt-4"`
2. Selects one based on routing strategy
3. Calls `litellm.completion(model=deployment.litellm_params.model, ...)`

**Example**: Model "gpt-4" maps to multiple deployments:
```yaml
- model_name: gpt-4
  litellm_params:
    model: gpt-4  # OpenAI

- model_name: gpt-4
  litellm_params:
    model: gpt-4-32k-deployment  # Azure OpenAI
```

Both respond to `router.completion(model="gpt-4")`.

## Cache Integration

Router maintains a **DualCache** for:

1. **Response caching**: Identical requests return cached response
2. **Rate limit tracking**: TPM/RPM counts per deployment
3. **Deployment cooldowns**: Temporarily skip failed deployments

```python
router.cache.get_or_set(
    key=f"completion_cache:{model}:{messages_hash}",
    fetch_fn=lambda: litellm.completion(...)
)
```

## Router in the Proxy

The proxy uses the Router internally:

```
Proxy endpoint
    ↓
auth/rate limiting
    ↓
router.acompletion()  # ← Handles routing + failover
    ↓
Response to client
```

The Proxy layer adds:
- Proxy-level authentication (JWT, API keys)
- Proxy-level rate limiting (per user, per team)
- Proxy-level cost tracking
- Admin APIs for deployment management

The Router handles:
- Model selection
- Provider failover
- Load balancing

## Monitoring

Router tracks metrics per deployment:

- `completion_requests` — Total requests
- `completion_latency_[p50|p99]` — Response time percentiles
- `completion_failures` — Failed requests
- `completion_cache_hits` — Cache hit rate

These are exposed via metrics endpoints for Prometheus scraping.

## Performance Optimization

### Connection Pooling
Router maintains HTTP connection pools per deployment to avoid TCP handshake overhead.

### Response Caching
Identical requests are cached (default 24 hours), eliminating provider calls.

### Pre-warming
Background health checks keep deployments warm and track latency.

