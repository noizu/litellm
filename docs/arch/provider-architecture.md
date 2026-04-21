# Provider Architecture

How LiteLLM supports 100+ LLM providers through a unified interface with minimal code duplication.

## Overview

Each provider implementation has:
1. **Provider config** — Model mappings, API endpoint
2. **Request transformation** — Convert to provider-specific format
3. **Response transformation** — Convert back to OpenAI format
4. **Error handling** — Map provider errors to OpenAI exceptions

```
Provider Registry
    ↓
Select provider based on model
    ↓
Load provider transformation module
    ↓
Transform request
    ↓
Make HTTP call
    ↓
Transform response
    ↓
Return unified format
```

## File Structure

```
litellm/llms/
├── __init__.py                 # Provider registry
├── base.py                     # Base classes for all providers
├── custom_httpx/
│   ├── llm_http_handler.py    # Central HTTP handler
│   └── http_handler.py         # Low-level httpx wrapper
│
├── openai/                     # OpenAI provider (GPT-4, GPT-3.5)
│   ├── __init__.py
│   ├── chat/
│   │   ├── __init__.py
│   │   └── transformation.py   # Request/response transformation
│   └── embedding/
│       └── transformation.py
│
├── anthropic/                  # Anthropic provider (Claude)
│   ├── __init__.py
│   ├── chat/transformation.py
│   └── embedding/transformation.py
│
├── google/                     # Google provider (Gemini, PaLM)
│   ├── __init__.py
│   ├── chat/transformation.py
│   └── embedding/transformation.py
│
└── [70+ other providers]       # Azure, AWS, Meta, Cohere, etc.
```

## Provider Registration

### Dynamic Provider Discovery

```python
# In llms/__init__.py

PROVIDER_MAP = {
    "openai": "llms.openai",
    "anthropic": "llms.anthropic",
    "google": "llms.google",
    ...
}

MODEL_MAP = {
    "gpt-4": "openai",
    "gpt-3.5-turbo": "openai",
    "claude-3-opus": "anthropic",
    "gemini-pro": "google",
    ...
}

# Lazy loading: module imported on first use
def get_provider(provider_name):
    module = __import__(PROVIDER_MAP[provider_name])
    return module.ProviderConfig
```

### Registration Pattern

Each provider implements a `ProviderConfig` class:

```python
# In llms/openai/chat/transformation.py

class ProviderConfig:
    @staticmethod
    def transform_request(
        model: str,
        messages: List[Dict],
        temperature: Optional[float],
        ...
    ) -> Dict:
        """Convert LiteLLM format to provider format"""
        return {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            ...
        }
    
    @staticmethod
    def transform_response(
        response: Dict,
        model: str
    ) -> ModelResponse:
        """Convert provider response to LiteLLM format"""
        return ModelResponse(
            id=response["id"],
            created=response["created"],
            choices=[...],
            usage=CompletionUsage(...)
        )
```

## Request Transformation

### Input: Unified LiteLLM Format

```python
{
    "model": "gpt-4",
    "messages": [
        {"role": "user", "content": "Hello"}
    ],
    "temperature": 0.7,
    "top_p": 0.9,
    "max_tokens": 100,
    "stream": False,
    "functions": [
        {
            "name": "get_weather",
            "description": "...",
            "parameters": {...}
        }
    ]
}
```

### Output: Provider-Specific Format

#### OpenAI Format (mostly same)
```json
{
    "model": "gpt-4",
    "messages": [...],
    "temperature": 0.7,
    "top_p": 0.9,
    "max_tokens": 100,
    "stream": false,
    "functions": [...]
}
```

#### Anthropic Claude Format (different)
```json
{
    "model": "claude-3-opus-20240229",
    "messages": [
        {"role": "user", "content": "Hello"}
    ],
    "max_tokens": 100,
    "temperature": 0.7,
    "top_p": 0.9,
    "tools": [  ← Uses "tools", not "functions"
        {
            "name": "get_weather",
            "description": "...",
            "input_schema": {...}  ← Different structure
        }
    ]
}
```

#### Google Gemini Format (very different)
```json
{
    "model": "models/gemini-pro",
    "contents": [
        {
            "role": "user",
            "parts": [
                {"text": "Hello"}  ← Nested structure
            ]
        }
    ],
    "generationConfig": {
        "temperature": 0.7,
        "maxOutputTokens": 100,
        "topP": 0.9
    }
}
```

### Transformation Example

```python
# In llms/anthropic/chat/transformation.py

class ProviderConfig:
    @staticmethod
    def transform_request(
        model: str,
        messages: List[Dict],
        temperature: Optional[float],
        max_tokens: Optional[int],
        functions: Optional[List[Dict]],
        **kwargs
    ) -> Dict:
        # Map model name to Anthropic model
        anthropic_model = model.replace("claude-", "claude-3-")
        
        # Transform tools
        tools = None
        if functions:
            tools = [
                {
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func["parameters"]  # Different field name
                }
                for func in functions
            ]
        
        return {
            "model": anthropic_model,
            "messages": messages,
            "max_tokens": max_tokens,  # Required for Anthropic
            "temperature": temperature,
            "tools": tools,
            **kwargs
        }
```

## Response Transformation

### Input: Provider Response

Each provider has a unique response format:

#### OpenAI Response
```json
{
    "id": "chatcmpl-...",
    "created": 1234567890,
    "model": "gpt-4",
    "choices": [
        {
            "message": {
                "role": "assistant",
                "content": "...",
                "tool_calls": [...]
            },
            "finish_reason": "stop",
            "index": 0
        }
    ],
    "usage": {
        "prompt_tokens": 10,
        "completion_tokens": 15,
        "total_tokens": 25
    }
}
```

#### Anthropic Response
```json
{
    "id": "msg_...",
    "type": "message",
    "role": "assistant",
    "content": [
        {
            "type": "text",
            "text": "..."
        },
        {
            "type": "tool_use",
            "id": "...",
            "name": "...",
            "input": {...}
        }
    ],
    "model": "claude-3-opus-20240229",
    "stop_reason": "end_turn",
    "stop_sequence": null,
    "usage": {
        "input_tokens": 10,
        "output_tokens": 15
    }
}
```

### Output: Unified LiteLLM Format

All providers return this format:

```python
ModelResponse(
    id="...",
    created=1234567890,
    model="gpt-4",
    choices=[
        Choice(
            message=Message(
                role="assistant",
                content="...",
                tool_calls=[...]
            ),
            finish_reason="stop",
            index=0
        )
    ],
    usage=CompletionUsage(
        prompt_tokens=10,
        completion_tokens=15,
        total_tokens=25
    )
)
```

### Transformation Example

```python
# In llms/anthropic/chat/transformation.py

class ProviderConfig:
    @staticmethod
    def transform_response(response: Dict, model: str) -> ModelResponse:
        # Extract message content
        content = ""
        tool_calls = []
        
        for block in response["content"]:
            if block["type"] == "text":
                content = block["text"]
            elif block["type"] == "tool_use":
                tool_calls.append({
                    "id": block["id"],
                    "function": {
                        "name": block["name"],
                        "arguments": json.dumps(block["input"])
                    },
                    "type": "function"
                })
        
        # Normalize usage
        usage = CompletionUsage(
            prompt_tokens=response["usage"]["input_tokens"],
            completion_tokens=response["usage"]["output_tokens"],
            total_tokens=response["usage"]["input_tokens"] + response["usage"]["output_tokens"]
        )
        
        return ModelResponse(
            id=response["id"],
            created=int(time.time()),
            model=model,
            choices=[
                Choice(
                    message=Message(
                        role="assistant",
                        content=content,
                        tool_calls=tool_calls if tool_calls else None
                    ),
                    finish_reason=response["stop_reason"],
                    index=0
                )
            ],
            usage=usage
        )
```

## Error Handling

Providers raise different exceptions. LiteLLM maps them to OpenAI format:

```python
# In llms/base.py or provider-specific modules

PROVIDER_ERROR_MAP = {
    "openai": {
        401: APIError("Unauthorized"),
        429: RateLimitError("Rate limited"),
        500: APIError("Server error"),
    },
    "anthropic": {
        401: APIError("Unauthorized"),
        429: RateLimitError("Rate limited"),
        529: APIError("Overloaded"),
    },
}

def map_error(provider: str, status_code: int, message: str):
    if provider in PROVIDER_ERROR_MAP:
        error_class = PROVIDER_ERROR_MAP[provider].get(status_code)
        if error_class:
            return error_class(message)
    
    # Default to generic error
    return APIError(f"Provider {provider}: {message}")
```

## Streaming Responses

For streaming requests, providers send chunks. Each is transformed:

```python
# Streaming flow

while True:
    chunk = await http_response.aiter_lines()
    
    # Parse provider-specific format
    data = provider.parse_streaming_chunk(chunk)
    
    # Transform to OpenAI format
    litellm_chunk = provider.transform_streaming_chunk(data)
    
    yield litellm_chunk
```

**Example**: OpenAI sends SSE, Anthropic sends JSON lines

```python
# OpenAI
data: {"choices":[{"delta":{"content":"Hello"}}]}

# Anthropic
{"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello"}}
```

## Embeddings Support

Most providers also support embeddings:

```python
# in llms/{provider}/embedding/transformation.py

class ProviderConfig:
    @staticmethod
    def transform_embedding_request(...):
        # Transform to provider format
        pass
    
    @staticmethod
    def transform_embedding_response(...):
        # Transform to OpenAI embedding format
        pass
```

## Adding a New Provider

1. **Create directory**: `litellm/llms/my_provider/`
2. **Implement transformation**:
   ```python
   # llms/my_provider/chat/transformation.py
   class ProviderConfig:
       @staticmethod
       def transform_request(...): ...
       
       @staticmethod
       def transform_response(...): ...
   ```
3. **Register in MODEL_MAP**:
   ```python
   # llms/__init__.py
   MODEL_MAP = {
       ...
       "my-model": "my_provider",
   }
   ```
4. **Add tests**: `tests/llm_translation/test_my_provider.py`

## Performance Optimization

### Connection Reuse
Each provider maintains an HTTP connection pool:
```python
http_client = httpx.AsyncClient(
    limits=PoolLimits(max_connections=100),
    timeout=Timeout(10.0, connect=5.0)
)
```

### Parallel Requests
Router can send requests to multiple providers in parallel for speed:
```python
# Try OpenAI and Anthropic in parallel
results = await asyncio.gather(
    openai_handler.completion(...),
    anthropic_handler.completion(...),
    return_exceptions=True
)
```

