# Project Layout

LiteLLM is a unified interface for 100+ LLM providers with a core library, proxy server, and observability integrations.

```
litellm/
├── litellm/                    # Core library → [layout/litellm.md](layout/litellm.md)
│   ├── main.py                 #   Main completion() function entrypoint
│   ├── proxy/                  #   Proxy server (FastAPI application)
│   ├── router.py               #   Load balancing and fallback logic
│   ├── llms/                   #   Provider implementations (100+ LLM vendors)
│   ├── caching/                #   Cache backends (Redis, in-memory, S3)
│   ├── integrations/           #   Observability, logging, monitoring
│   ├── types/                  #   Pydantic models and type hints
│   └── [27 other modules]      #   See layout/litellm.md for details
│
├── enterprise/                 # Enterprise features
│   ├── litellm_enterprise/     #   Enterprise-specific code and models
│   ├── enterprise_hooks/       #   Custom hooks and callbacks
│   ├── enterprise_ui/          #   Enterprise dashboard
│   └── cloudformation_stack/   #   AWS deployment templates
│
├── ui/                         # Frontend dashboard (Next.js)
│   └── litellm-dashboard/      #   React/TypeScript UI for proxy management
│
├── litellm-js/                 # JavaScript integration
│   ├── proxy/                  #   Proxy API client
│   └── spend-logs/             #   Spend tracking library
│
├── litellm-proxy-extras/       # Extended proxy features
│   ├── litellm_proxy_extras/   #   Additional proxy functionality
│   └── tests/                  #   Proxy-specific tests
│
├── tests/                      # Test suite → [layout/tests.md](layout/tests.md)
│   ├── test_litellm/           #   Unit tests for core library
│   ├── llm_translation/        #   Provider integration tests
│   ├── proxy_unit_tests/       #   Proxy server tests
│   ├── load_tests/             #   Performance benchmarks
│   └── [10+ other test dirs]   #   See layout/tests.md for details
│
├── deploy/                     # Deployment configurations
│   ├── kubernetes/             #   K8s manifests and Helm charts
│   ├── charts/                 #   Helm chart definitions
│   └── azure_resource_manager/ #   ARM templates
│
├── docker/                     # Docker configuration
│   ├── Dockerfile              #   Main container image
│   ├── docker-compose.yml      #   Local development stack
│   ├── docker-compose.hardened.yml  # Hardened production config
│   ├── build_from_pip/         #   Alternative Docker builds
│   └── tests/                  #   Docker test suite
│
├── cookbook/                   # Examples and guides → [layout/cookbook.md](layout/cookbook.md)
│   ├── litellm_proxy_server/   #   Proxy server examples
│   ├── litellm_router/         #   Router usage examples
│   ├── logging_observability/  #   Integration examples
│   ├── benchmark/              #   Performance testing guides
│   └── [11 other examples]     #   See layout/cookbook.md for details
│
├── ci_cd/                      # CI/CD configuration
│   └── [CircleCI config]       #   Build and test automation
│
├── db_scripts/                 # Database utilities
│   └── [migration and setup scripts]
│
├── scripts/                    # Build and utility scripts
│   └── health_check/           #   Health check utilities
│
├── docs/                       # Documentation
│   └── my-website/             #   Release notes and guides
│
├── .github/                    # GitHub configuration
│   ├── workflows/              #   GitHub Actions
│   ├── ISSUE_TEMPLATE/         #   Issue templates
│   └── pull_request_template.md
│
├── .circleci/                  # CircleCI pipeline configuration
├── .devcontainer/              # Dev container setup (Docker + VS Code)
├── .semgrep/                   # Semgrep security rules
│
├── pyproject.toml              # Python project config (dependencies, build)
├── Makefile                    # Development commands (install, test, lint)
├── package.json                # npm/Node dependencies (UI, tools)
├── docker-compose.yml          # Local dev services (PostgreSQL, Redis, etc.)
├── Dockerfile                  # Production container
├── .env.example                # Environment template — copy to .env
├── .flake8                     # Flake8 linting config
├── ruff.toml                   # Ruff linter config
├── pyrightconfig.json          # Pyright type checker config
├── codecov.yaml                # Code coverage config
├── .gitignore                  # Git ignore rules
│
├── README.md                   # Start here — project overview
├── CLAUDE.md                   # Development guide and patterns
├── ARCHITECTURE.md             # System design and components
├── CONTRIBUTING.md             # Contribution guidelines
├── AGENTS.md                   # LLM agents documentation
├── GEMINI.md                   # Gemini-specific notes
├── security.md                 # Security policies
│
├── prometheus.yml              # Prometheus metrics config
├── proxy_server_config.yaml    # Example proxy configuration
├── dev_config.yaml             # Development configuration
├── provider_endpoints_support.json  # Supported endpoints per provider
├── model_prices_and_context_window.json  # Model metadata
├── mcp_servers.json            # MCP server definitions
│
└── LICENSE                     # MIT License
```

## Key Files Requiring Setup

| File | Action |
|------|--------|
| `.env` | Copy from `.env.example`, add API keys and database URL |
| `pyproject.toml` | Defines Python dependencies via uv/pip |
| `docker-compose.yml` | Provides local PostgreSQL, Redis, and other services |
| `proxy_server_config.yaml` | Proxy server configuration (models, auth, monitoring) |

## Quick Links

- **Start developing**: Read [CLAUDE.md](../CLAUDE.md) for installation, testing, and code style
- **Understand architecture**: See [ARCHITECTURE.md](../ARCHITECTURE.md)
- **Run proxy server**: Use `docker-compose.yml` or `litellm/proxy/proxy_server.py`
- **Contributing**: Check [CONTRIBUTING.md](../CONTRIBUTING.md) and [AGENTS.md](../AGENTS.md)

