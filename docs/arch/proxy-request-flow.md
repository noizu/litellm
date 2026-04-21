# Proxy Request Flow (Detailed)

The AI Gateway request flow with authentication, rate limiting, routing, and cost tracking.

## Sequence Diagram

```
Client Request
    ↓
┌─────────────────────────────────────────┐
│ proxy/proxy_server.py                   │
│  chat_completion() endpoint             │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ proxy/auth/                             │
│  user_api_key_auth()                    │
│  - Check API key cache (Redis)          │
│  - Fetch from DB if cache miss          │
│  - Verify spend limits                  │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ proxy/hooks/                            │
│  max_budget_limiter()                   │
│  parallel_request_limiter()             │
│  - Check TPM/RPM counters (Redis)       │
│  - Increment request counter            │
│  - Enforce budget limits                │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ proxy/route_llm_request.py              │
│  route_request()                        │
│  - Select model deployment              │
│  - Select load balancing strategy       │
│  - Build provider config                │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ router.py                               │
│  Router.acompletion() or direct SDK     │
│  - Check response cache (Redis)         │
│  - Route to best provider               │
│  - Handle fallbacks                     │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ main.py                                 │
│  litellm.acompletion()                  │
│  - Get provider from model name         │
│  - Call BaseLLMHTTPHandler              │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ llms/custom_httpx/llm_http_handler.py  │
│  BaseLLMHTTPHandler.completion()        │
│  - Transform request to provider format │
│  - Make HTTP call                       │
│  - Transform response to OpenAI format  │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ llms/{provider}/chat/transformation.py │
│  transform_request()  ────▶  Provider   │
│                     ◀──  transform_response()
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ Response Processing (main.py wrapper)   │
│  - Calculate cost (from token counts)   │
│  - Update response metadata             │
│  - Store cost in hidden_params          │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ proxy/common_request_processing.py      │
│  - Extract cost from hidden_params      │
│  - Add x-litellm-response-cost header   │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ Async Logging (non-blocking)            │
│  logging_obj.async_success_handler()    │
│  - Trigger callbacks (LangSmith, etc.)  │
│  - Call _ProxyDBLogger                  │
│  - Queue spend to Redis                 │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ Response to Client                      │
│  - ModelResponse + headers              │
└─────────────────────────────────────────┘
    ↓ (Background, every 60s)
┌─────────────────────────────────────────┐
│ db/db_spend_update_writer.py            │
│  Flush Redis spend queue to PostgreSQL  │
└─────────────────────────────────────────┘
```

## Key Components

### 1. Authentication (`proxy/auth/`)
- **File**: `proxy/auth/user_api_key_auth.py`
- **Input**: API key from request headers
- **Output**: User ID, team ID, spend limits
- **Caching**: Redis cache with fallback to PostgreSQL
- **Methods Supported**: API keys, JWT, OAuth2

### 2. Rate Limiting (`proxy/hooks/`)
- **File**: `parallel_request_limiter_v3.py`
- **Counters**: Per API key, per user, per team (in Redis)
- **Limits**: TPM (tokens per minute), RPM (requests per minute)
- **Enforcement**: Reject request if limit exceeded

### 3. Routing (`proxy/route_llm_request.py`)
- **Input**: Model name, routing configuration
- **Output**: Provider name, provider config
- **Strategies**: Weighted shuffle, least busy, cost-based
- **Fallback**: Try next provider if first fails

### 4. Provider Transformation (`llms/{provider}/chat/`)
- **Input**: Unified LiteLLM request format
- **Output**: Provider-specific request format
- **Example**: Convert `litellm.message_to_prompt_dict()` to OpenAI, Anthropic, Google formats
- **Response**: Convert provider response back to OpenAI format

### 5. Cost Calculation (`cost_calculator.py`)
- **Input**: Model name, token counts (completion + prompt)
- **Output**: Cost in USD
- **Data**: Uses `model_prices_and_context_window.json`
- **Timing**: Synchronous, happens before response sent to client

### 6. Async Logging
- **Non-blocking**: Happens after response returned
- **Destinations**: Database, callbacks (LangSmith, Datadog), webhooks
- **Cost Storage**: Queued to Redis, batched to PostgreSQL every 60s

## Cost Attribution Flow

```
LLM Response (from provider)
    ↓
Extract token counts
    ↓
litellm.completion_cost() → USD cost
    ↓
response._hidden_params["response_cost"] = cost
    ↓
Extract cost in proxy endpoint
    ↓
Add x-litellm-response-cost response header
    ↓
Async callback: DBSpendUpdateWriter.queue_spend()
    ↓
Redis queue: spend_updates:{key_id}
    ↓
Background job (every 60s): Flush to PostgreSQL
```

## Error Handling

1. **Auth Failure** → 401 Unauthorized
2. **Rate Limit Exceeded** → 429 Too Many Requests
3. **Provider Unavailable** → 503 Service Unavailable (if no fallback) or fallback
4. **Invalid Request** → 400 Bad Request
5. **Provider Error** → Mapped to OpenAI error format

## Streaming Responses

For streaming requests (`stream: true`):
- Response headers sent immediately
- Chunks streamed as they arrive from provider
- Cost calculation deferred until stream completes
- Async logging still triggered after stream ends

