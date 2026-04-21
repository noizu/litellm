# SDK Request Flow

How the core LiteLLM SDK (`litellm/`) processes completion requests independently of the proxy.

## Overview

SDK users call `litellm.completion()` or `litellm.acompletion()` directly:

```python
import litellm

response = await litellm.acompletion(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)

print(response["choices"][0]["message"]["content"])
```

The SDK handles:
- Provider resolution (model name → provider API)
- Request transformation (LiteLLM format → provider format)
- HTTP calls
- Response parsing
- Error handling
- Streaming (if requested)

## Request Flow Diagram

```
litellm.acompletion(model="gpt-4", ...)
    ↓
main.py: acompletion() function
    ↓
utils.py: get_llm_provider(model)
    → Resolve "gpt-4" to "openai" provider
    → Return ProviderConfig
    ↓
llms/custom_httpx/llm_http_handler.py
    → BaseLLMHTTPHandler.completion()
    ↓
llms/{provider}/chat/transformation.py
    → TransformRequest: Convert input to provider format
    ↓
httpx (HTTP client)
    → Send request to LLM provider API
    ← Receive response
    ↓
llms/{provider}/chat/transformation.py
    → TransformResponse: Convert to OpenAI format
    ↓
litellm_core_utils/streaming_handler.py
    → Handle streaming if requested
    ↓
Return ModelResponse object
    ↓
Optional async callbacks (logging, LangSmith, etc.)
```

## Key Components

### 1. Entry Point (`main.py`)

**Function**: `completion()`, `acompletion()`

**Signature**:
```python
async def acompletion(
    model: str,
    messages: List[Dict],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    stream: bool = False,
    **kwargs
) -> Union[ModelResponse, AsyncIterator[ModelResponse]]:
    pass
```

**Responsibilities**:
- Validate inputs
- Resolve model → provider
- Call HTTP handler
- Handle exceptions
- Update response metadata

### 2. Provider Resolution (`utils.py`)

**Function**: `get_llm_provider(model: str)`

**Input**: Model name (e.g., "gpt-4", "claude-3-opus")

**Output**: Provider class (e.g., "openai", "anthropic")

**Mapping**: Hardcoded in `utils.py` or from config

```python
MODEL_MAP = {
    "gpt-4": "openai",
    "gpt-3.5-turbo": "openai",
    "claude-3-opus": "anthropic",
    "gemini-pro": "google",
    ...
}
```

### 3. HTTP Handler (`llms/custom_httpx/llm_http_handler.py`)

**Class**: `BaseLLMHTTPHandler`

**Method**: `completion()`

**Responsibilities**:
1. Call provider's `transform_request()`
2. Build HTTP request (URL, headers, body)
3. Make HTTP call via `httpx`
4. Receive response
5. Call provider's `transform_response()`
6. Return ModelResponse

**Example Flow**:
```python
class BaseLLMHTTPHandler:
    async def completion(self, model, messages, ...):
        # 1. Transform request
        provider_request = ProviderConfig.transform_request(
            model=model,
            messages=messages,
            ...
        )
        
        # 2. Make HTTP call
        response = await self.http_client.post(
            url=provider_request.url,
            headers=provider_request.headers,
            json=provider_request.body
        )
        
        # 3. Transform response
        model_response = ProviderConfig.transform_response(
            response=response.json(),
            model=model
        )
        
        # 4. Return
        return model_response
```

### 4. Provider-Specific Transformation (`llms/{provider}/chat/transformation.py`)

Each provider has a transformation module:

**Transform Request**:
```
LiteLLM request format
    ↓
provider.transform_request()
    ↓
Provider-specific request format
```

**Example**: OpenAI vs Claude

```python
# LiteLLM unified format
{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hi"}],
    "temperature": 0.5,
    "max_tokens": 100
}

# OpenAI format (same, basically)
{
    "model": "gpt-4",
    "messages": [...],
    "temperature": 0.5,
    "max_tokens": 100
}

# Anthropic format (different!)
{
    "model": "claude-3-opus",
    "messages": [{"role": "user", "content": "Hi"}],
    "max_tokens": 100,  # Required, not optional
    "temperature": 0.5
}
```

**Transform Response**:
```
Provider response format
    ↓
provider.transform_response()
    ↓
LiteLLM ModelResponse format
```

### 5. Streaming Handler (`litellm_core_utils/streaming_handler.py`)

For `stream=True` requests:

```python
async def stream_response():
    async with httpx.stream(...) as response:
        async for line in response.aiter_lines():
            # Parse SSE chunk
            chunk = parse_streaming_chunk(line)
            
            # Convert to LiteLLM format
            litellm_chunk = transform_chunk(chunk, provider)
            
            yield litellm_chunk
```

**Output**: AsyncIterator of ModelResponse chunks

**Client Usage**:
```python
response = await litellm.acompletion(
    model="gpt-4",
    messages=[...],
    stream=True
)

async for chunk in response:
    print(chunk["choices"][0]["delta"].get("content", ""))
```

## Error Handling

Exceptions are caught and mapped to OpenAI format:

```python
try:
    response = await http_call()
except ProviderSpecificException as e:
    # Map to OpenAI exception
    raise APIStatusCodeException(
        status_code=e.status_code,
        message=str(e),
        llm_provider=provider
    )
```

**Common Errors**:
- 401 → Invalid API key
- 429 → Rate limited
- 500 → Provider server error
- Timeout → Network issue

## Response Format (ModelResponse)

All providers return a unified `ModelResponse`:

```python
class ModelResponse:
    id: str
    created: int
    model: str
    choices: List[Choice]
    usage: CompletionUsage
    
    # Hidden params (internal use)
    _hidden_params: Dict
    # - response_cost: float (calculated in proxy)
    # - llm_calls: List (for routing info)
```

**Example Response**:
```json
{
    "id": "chatcmpl-123",
    "created": 1234567890,
    "model": "gpt-4",
    "choices": [{
        "message": {
            "role": "assistant",
            "content": "Hello! How can I help?"
        },
        "finish_reason": "stop",
        "index": 0
    }],
    "usage": {
        "prompt_tokens": 10,
        "completion_tokens": 15,
        "total_tokens": 25
    }
}
```

## Async Callbacks (Optional)

After response returns, async callbacks can be triggered:

```python
# In litellm_logging.py
response = await litellm.acompletion(...)

# Trigger callbacks async (don't block)
asyncio.create_task(
    logging_obj.async_success_handler(
        model, response, messages, ...
    )
)

return response
```

**Callbacks Used For**:
- Logging (LangSmith, Datadog, custom)
- Analytics
- Cost tracking
- Audit trails

## Performance Optimization

### Connection Pooling
HTTP client reuses connections per provider:

```python
http_client = httpx.AsyncClient(
    pool_limits=PoolLimits(max_connections=100)
)
```

### Request Timeouts
Default timeouts prevent hung requests:

```python
timeout = httpx.Timeout(
    timeout=10.0,  # seconds
    connect=5.0
)
```

### Retries
Automatic retries on transient failures (429, 5xx):

```python
max_retries = 3
for attempt in range(max_retries):
    try:
        return await http_call()
    except TransientError:
        if attempt == max_retries - 1:
            raise
        await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

## Caching (Optional)

Responses can be cached to avoid redundant provider calls:

```python
response = await litellm.acompletion(
    model="gpt-4",
    messages=[...],
    caching={
        "type": "redis",  # or "in_memory", "s3"
        "ttl": 3600  # seconds
    }
)
```

**Cache Key**: Hash of (model, messages, temperature, etc.)

**Cache Hit**: Return cached response without calling provider

