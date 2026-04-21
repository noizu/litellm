# Cookbook: Examples and Guides

Real-world examples, tutorials, and reference implementations for LiteLLM features.

```
cookbook/
├── litellm_proxy_server/       # Proxy server examples
│   ├── example_config_yaml/    #   Configuration templates
│   ├── docker_compose/         #   Docker Compose setups
│   └── [other proxy examples]
│
├── litellm_router/             # Router usage patterns
│   ├── basic_router.py         #   Simple load balancing
│   ├── fallback_example.py     #   Fallback strategies
│   └── [other router examples]
│
├── logging_observability/      # Integration examples
│   ├── langsmith_integration.py #  LangSmith logging
│   ├── datadog_integration.py  #   Datadog observability
│   ├── opentelemetry_example.py #  OpenTelemetry setup
│   └── [other logging examples]
│
├── benchmark/                  # Performance testing
│   ├── load_testing.py         #   Load test scripts
│   ├── latency_testing.py      #   Latency measurement
│   └── throughput_testing.py   #   Throughput benchmarks
│
├── ai_coding_tool_guides/      # AI coding tool integration
│   ├── vscode_setup.md         #   VS Code setup
│   ├── cursor_setup.md         #   Cursor IDE setup
│   └── [other IDE guides]
│
├── litellm_router_load_test/   # Router load testing
│   └── [load test suite]
│
├── anthropic_agent_sdk/        # Anthropic Agents example
│   └── [agent implementation]
│
├── livekit_agent_sdk/          # LiveKit agent integration
│   └── [LiveKit SDK example]
│
├── misc/                       # Miscellaneous examples
│   ├── function_calling.py     #   Function calling patterns
│   ├── streaming.py            #   Streaming responses
│   ├── vision.py               #   Vision model usage
│   ├── embeddings.py           #   Embedding examples
│   └── [other misc examples]
│
├── community-resources/        # Community contributions
│   └── [user-contributed examples]
│
├── gollem_go_agent_framework/  # GoAgent framework
│   └── [GoAgent integration]
│
├── litellm-ollama-docker-image/ # Ollama integration
│   └── [Ollama setup]
│
├── codellama-server/           # CodeLlama server
│   └── [CodeLlama setup]
│
├── mock_guardrail_server/      # Guardrail mock server
│   ├── example_guardrail.py    #   Guardrail implementation
│   └── [guardrail patterns]
│
├── mock_prompt_management_server/ # Prompt management mock
│   └── [prompt management patterns]
│
└── README.md                   # Cookbook overview
```

## Key Examples

### Getting Started
- **Router**: Basic load balancing and fallback setup
- **Proxy**: Running the proxy server with example configs
- **Logging**: Setting up observability (LangSmith, Datadog, OpenTelemetry)

### Advanced Features
- **Function Calling**: Using function calling with different providers
- **Streaming**: Handling streaming responses
- **Vision**: Using vision models (GPT-4 Vision, Claude Vision, etc.)
- **Embeddings**: Embedding generation and search
- **RAG**: Retrieval-Augmented Generation patterns

### Integration
- **LangChain**: LangChain integration patterns
- **LangSmith**: Observability and debugging with LangSmith
- **OpenTelemetry**: Standard observability setup
- **AI Coding Tools**: Integration with VS Code, Cursor, and other IDEs

### Deployment
- **Docker Compose**: Local development stack
- **Kubernetes**: K8s deployment manifests
- **AWS**: Deployment on AWS
- **Azure**: Deployment on Azure

## Running Examples

Most examples are standalone Python scripts:

```bash
cd cookbook/<directory>
uv run python example_script.py
```

Some require configuration or environment variables — check the README in each subdirectory.

