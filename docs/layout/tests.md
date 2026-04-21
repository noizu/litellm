# Test Structure

Comprehensive test suites for all LiteLLM components.

```
tests/
├── test_litellm/               # Unit tests for core library
│   ├── test_completion.py      #   Core completion() function tests
│   ├── test_router.py          #   Router logic tests
│   ├── test_caching.py         #   Caching mechanism tests
│   ├── test_embeddings.py      #   Embedding function tests
│   └── [50+ other test files]
│
├── llm_translation/            # Provider integration tests
│   ├── test_openai.py          #   OpenAI integration tests
│   ├── test_anthropic.py       #   Anthropic/Claude tests
│   ├── test_google.py          #   Google Gemini tests
│   ├── test_azure.py           #   Azure OpenAI tests
│   └── [50+ other provider tests]
│
├── proxy_unit_tests/           # Proxy server unit tests
│   ├── test_auth.py            #   Authentication tests
│   ├── test_db_models.py       #   Database model tests
│   ├── test_management_api.py  #   Admin endpoint tests
│   └── [other proxy unit tests]
│
├── proxy_admin_ui_tests/       # Proxy dashboard tests
│   ├── test_admin_endpoints.py #   Admin API tests
│   └── test_ui_api.py          #   UI-specific endpoint tests
│
├── basic_proxy_startup_tests/  # Proxy startup validation
│   └── [startup and basic config tests]
│
├── load_tests/                 # Performance benchmarks
│   ├── test_throughput.py      #   Throughput benchmarks
│   ├── test_latency.py         #   Latency measurements
│   └── [other load tests]
│
├── logging_callback_tests/     # Integration callback tests
│   ├── test_langsmith.py       #   LangSmith logging
│   ├── test_datadog.py         #   Datadog integration
│   └── [other callback tests]
│
├── pass_through_tests/         # Provider pass-through tests
│   └── [pass-through request tests]
│
├── pass_through_unit_tests/    # Unit tests for pass-through logic
│   └── [unit tests for forwarding]
│
├── openai_endpoints_tests/     # OpenAI-compatible endpoints
│   ├── test_chat_completion.py #   Chat completion compatibility
│   ├── test_embeddings.py      #   Embeddings endpoint
│   └── [other OpenAI endpoint tests]
│
├── llm_responses_api_testing/  # Response parsing tests
│   └── [LLM response format tests]
│
├── vector_store_tests/         # Vector store integration tests
│   └── [vector store functionality tests]
│
├── otel_tests/                 # OpenTelemetry tests
│   └── [observability tests]
│
├── agent_tests/                # Agent functionality tests
│   └── [agent integration tests]
│
├── enterprise/                 # Enterprise feature tests
│   └── [enterprise-specific tests]
│
├── documentation_tests/        # Documentation validation
│   └── [doc and example validation]
│
├── unified_google_tests/       # Unified Google provider tests
│   └── [Google-specific tests]
│
└── litellm_utils_tests/        # Utility function tests
    └── [utility function tests]
```

## Test Running

**Run all tests:**
```bash
make test
```

**Run specific test file:**
```bash
uv run pytest tests/path/to/test_file.py -v
```

**Run specific test function:**
```bash
uv run pytest tests/path/to/test_file.py::test_function -v
```

**Unit tests only:**
```bash
make test-unit           # tests/test_litellm with 4 parallel workers
```

**Integration tests:**
```bash
make test-integration    # All tests except tests/test_litellm
```

## Test Patterns

### Key Files to Know

- `test_litellm/` — Core library behavior, unit tests
- `llm_translation/` — Provider integration, requires live API keys
- `proxy_unit_tests/` — Proxy server logic
- `load_tests/` — Performance and scalability

### Provider Tests

Each provider has corresponding integration tests in `llm_translation/test_<provider>.py`:
- Basic completion calls
- Streaming responses
- Function calling
- Token counting
- Error handling

### Proxy Tests

Proxy server tests cover:
- Authentication (API keys, JWT, OAuth)
- Database operations
- Admin endpoints (model management, budget tracking)
- Request routing and fallback
- Rate limiting and quotas

