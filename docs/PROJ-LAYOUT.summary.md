# Project Layout Summary

Quick reference of the LiteLLM repository structure.

```
litellm/
├── litellm/                    # Core library (100+ LLM providers)
│   ├── main.py                 # Completion function entry point
│   ├── router.py               # Load balancing and fallback
│   ├── llms/                   # Provider implementations
│   ├── proxy/                  # FastAPI proxy server
│   ├── caching/                # Cache backends
│   ├── integrations/           # Observability and logging
│   └── types/                  # Pydantic type definitions
├── enterprise/                 # Enterprise features and hooks
├── ui/litellm-dashboard/       # Next.js frontend dashboard
├── litellm-js/                 # JavaScript client library
├── litellm-proxy-extras/       # Extended proxy functionality
├── tests/                      # Comprehensive test suites
├── deploy/                     # Kubernetes and cloud deployment
├── docker/                     # Docker and container configs
├── docs/                       # Documentation and release notes
├── cookbook/                   # Examples and integration guides
├── scripts/                    # Build and utility scripts
├── db_scripts/                 # Database utilities
├── .github/                    # GitHub workflows and templates
├── .circleci/                  # CircleCI pipeline configuration
├── Makefile                    # Development commands
├── pyproject.toml              # Python dependencies and build config
├── docker-compose.yml          # Local dev services
├── Dockerfile                  # Production container
├── README.md                   # Project overview
├── CLAUDE.md                   # Development guide
├── ARCHITECTURE.md             # System design
├── CONTRIBUTING.md             # Contribution guidelines
├── AGENTS.md                   # LLM agents documentation
├── GEMINI.md                   # Gemini-specific notes
└── LICENSE                     # MIT License
```

