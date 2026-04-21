# LiteLLM Core Library Structure

The main `litellm/` directory contains the core library implementation.

```
litellm/
├── main.py                     # Core completion() function — main entry point
├── router.py                   # Router class for load balancing and fallback logic
├── router_strategy/            # Load balancing strategies
├── router_utils/               # Router utilities and helpers
│
├── llms/                       # Provider implementations (100+ LLM vendors)
│   ├── openai/                 #   OpenAI (GPT-4, GPT-3.5, etc.)
│   ├── anthropic/              #   Anthropic (Claude)
│   ├── google/                 #   Google (Gemini, PaLM)
│   ├── azure/                  #   Azure OpenAI
│   ├── aws/                    #   AWS (Bedrock, SageMaker)
│   ├── meta/                   #   Meta (Llama)
│   ├── cohere/                 #   Cohere
│   ├── huggingface/            #   Hugging Face
│   └── [70+ other providers]   #   Each provider has transformation functions
│
├── proxy/                      # Proxy server (FastAPI application)
│   ├── proxy_server.py         #   Main FastAPI app
│   ├── auth/                   #   Authentication (API keys, JWT, OAuth2)
│   ├── db/                     #   Database models and operations (Prisma)
│   ├── management_endpoints/   #   Admin APIs (keys, teams, models, budgets)
│   ├── pass_through_endpoints/ #   Provider-specific API forwarding
│   ├── guardrails/             #   Safety and content filtering hooks
│   ├── router.py               #   Proxy router configuration
│   ├── _experimental/          #   Experimental features (UI, agents)
│   └── schema.prisma           #   Database schema (PostgreSQL/SQLite)
│
├── caching/                    # Cache backends
│   ├── cache.py                #   Cache interface
│   ├── redis_cache.py          #   Redis backend
│   ├── in_memory_cache.py      #   In-memory backend
│   ├── s3_cache.py             #   AWS S3 backend
│   └── [other cache backends]
│
├── integrations/               # Third-party integrations
│   ├── langchain/              #   LangChain integration
│   ├── opentelemetry/          #   OpenTelemetry observability
│   ├── logging_callback_*.py   #   Logging callbacks (LangSmith, Datadog, etc.)
│   └── [20+ other integrations]
│
├── types/                      # Pydantic models and type definitions
│   ├── router.py               #   Router types
│   ├── llm_output.py           #   LLM response types
│   ├── completion.py           #   Completion request/response types
│   └── [other type definitions]
│
├── router_strategy/            # Load balancing strategies
│   ├── least_busy.py           #   Least busy first
│   ├── weighted_shuffling.py   #   Weighted random selection
│   └── [other strategies]
│
├── batch_completion/           # Batch processing
├── batches/                    # Batch API implementation
├── files/                      # File handling utilities
├── fine_tuning/                # Fine-tuning support
├── rerank_api/                 # Reranking API
├── search/                     # Search utilities
├── vector_stores/              # Vector store integrations
├── rag/                        # RAG (Retrieval-Augmented Generation)
├── embeddings/                 # Embedding functions
├── images/                     # Image processing utilities
├── vision/                     # Vision model support
├── audio/                      # Audio processing
├── videos/                     # Video processing
├── ocr/                        # Optical character recognition
│
├── anthropic_interface/        # Anthropic-specific features
├── google_genai/               # Google GenAI-specific features
├── a2a_protocol/               # Agent-to-Agent protocol
├── realtime_api/               # Real-time API support
├── assistants/                 # OpenAI Assistants API
│
├── compression/                # Response compression
├── endpoints/                  # HTTP endpoint utilities
├── responses/                  # Response parsing and formatting
├── passthrough/                # Pass-through request handling
├── containers/                 # Container utilities
│
├── proxy_auth/                 # Authentication utilities
├── secret_managers/            # Secret management (AWS, Azure, Vault)
├── completion_extras/          #Additional completion features
├── skills/                     # LLM skills/actions
├── interactions/               # Interaction tracking
│
├── evals/                      # Evaluation frameworks
├── experimental_mcp_client/    # MCP (Model Context Protocol) client
│
├── _logging.py                 # Logging configuration
├── utils.py                    # General utilities
├── litellm_core_utils/         # Core utility functions
│
└── __init__.py                 # Package initialization
```

## Key Modules

### Completion Flow
- **entry**: `main.py` → `completion()` function
- **routing**: `router.py` decides which provider/model to use
- **providers**: `llms/<provider>/` transforms requests and responses
- **output**: Unified response format

### Proxy Server
- **server**: `proxy/proxy_server.py` (FastAPI)
- **auth**: `proxy/auth/` manages API keys and tokens
- **db**: `proxy/db/` Prisma models for PostgreSQL/SQLite
- **endpoints**: `proxy/management_endpoints/` for admin APIs

### Caching
- **backends**: Redis, in-memory, S3, etc.
- **key**: Generated from model, input, parameters
- **invalidation**: TTL-based or manual

### Integrations
- **observability**: OpenTelemetry, Datadog, New Relic
- **frameworks**: LangChain, LlamaIndex, semantic-kernel
- **callbacks**: Custom logging and hooks

