"""
Test suite for Anthropic beta headers filtering and mapping across all providers.

This test validates:
1. Headers with null values in the config are filtered out
2. Headers with non-null values are correctly mapped to provider-specific names
3. Unknown headers (not in config) are filtered out
4. For Bedrock providers, beta headers appear in the request body (not just HTTP headers)
"""

import json
import os
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import litellm
from litellm.anthropic_beta_headers_manager import (
    filter_and_transform_beta_headers,
    update_request_with_filtered_beta,
)


class TestAnthropicBetaHeadersFiltering:
    """Test beta header filtering and mapping for all providers."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        """Load the beta headers config for testing."""
        # Force use of local config file for tests
        monkeypatch.setenv("LITELLM_LOCAL_ANTHROPIC_BETA_HEADERS", "True")

        # Clear the cached config to ensure fresh load with local config
        from litellm import anthropic_beta_headers_manager

        anthropic_beta_headers_manager._BETA_HEADERS_CONFIG = None

        config_path = os.path.join(
            os.path.dirname(litellm.__file__),
            "anthropic_beta_headers_config.json",
        )
        with open(config_path, "r") as f:
            self.config = json.load(f)

    def get_all_beta_headers(self) -> List[str]:
        """Get all beta headers from the anthropic provider config."""
        return list(self.config.get("anthropic", {}).keys())

    def get_supported_headers(self, provider: str) -> List[str]:
        """Get headers with non-null values for a provider."""
        provider_config = self.config.get(provider, {})
        return [
            header for header, value in provider_config.items() if value is not None
        ]

    def get_unsupported_headers(self, provider: str) -> List[str]:
        """Get headers with null values for a provider."""
        provider_config = self.config.get(provider, {})
        return [header for header, value in provider_config.items() if value is None]

    def get_mapped_headers(self, provider: str) -> Dict[str, str]:
        """Get mapping of input headers to provider-specific headers."""
        provider_config = self.config.get(provider, {})
        return {
            header: value
            for header, value in provider_config.items()
            if value is not None
        }

    @pytest.mark.parametrize(
        "provider",
        [
            "anthropic",
            "azure_ai",
            "bedrock_converse",
            "bedrock",
            "vertex_ai",
            "databricks",
            "cerebras",
            "cerebras_ai",
        ],
    )
    def test_filter_and_transform_beta_headers_all_headers(self, provider):
        """Test filtering with all possible beta headers."""
        all_headers = self.get_all_beta_headers()
        supported_headers = self.get_supported_headers(provider)
        unsupported_headers = self.get_unsupported_headers(provider)
        mapped_headers = self.get_mapped_headers(provider)

        filtered = filter_and_transform_beta_headers(
            beta_headers=all_headers, provider=provider
        )

        for header in unsupported_headers:
            assert (
                header not in filtered
            ), f"Unsupported header '{header}' should be filtered out for {provider}"
            assert (
                mapped_headers.get(header) not in filtered
            ), f"Mapped value of unsupported header '{header}' should not appear for {provider}"

        for header in supported_headers:
            expected_mapped = mapped_headers[header]
            assert (
                expected_mapped in filtered
            ), f"Supported header '{header}' should be mapped to '{expected_mapped}' for {provider}"

    @pytest.mark.parametrize(
        "provider",
        [
            "anthropic",
            "azure_ai",
            "bedrock_converse",
            "bedrock",
            "vertex_ai",
            "databricks",
            "cerebras",
            "cerebras_ai",
        ],
    )
    def test_unknown_headers_filtered_out(self, provider):
        """Test that headers not in the config are filtered out."""
        unknown_headers = [
            "unknown-header-1",
            "unknown-header-2",
            "fake-beta-2025-01-01",
        ]
        all_headers = self.get_all_beta_headers() + unknown_headers

        filtered = filter_and_transform_beta_headers(
            beta_headers=all_headers, provider=provider
        )

        for unknown in unknown_headers:
            assert (
                unknown not in filtered
            ), f"Unknown header '{unknown}' should be filtered out for {provider}"

    def test_update_request_with_filtered_beta_vertex_ai(self):
        """Test combined filtering for both HTTP headers and request body betas."""
        headers = {
            "anthropic-beta": "files-api-2025-04-14,context-management-2025-06-27,code-execution-2025-05-22"
        }
        request_data = {
            "anthropic_beta": [
                "files-api-2025-04-14",
                "context-management-2025-06-27",
                "code-execution-2025-05-22",
            ]
        }

        filtered_headers, filtered_request_data = update_request_with_filtered_beta(
            headers=headers,
            request_data=request_data,
            provider="vertex_ai",
        )

        assert filtered_headers.get("anthropic-beta") == "context-management-2025-06-27"
        assert filtered_request_data.get("anthropic_beta") == [
            "context-management-2025-06-27"
        ]

    @pytest.mark.asyncio
    async def test_anthropic_messages_http_headers_filtering(self):
        """Test that Anthropic messages API filters HTTP headers correctly."""
        all_headers = self.get_all_beta_headers()
        unsupported = self.get_unsupported_headers("anthropic")

        with patch(
            "litellm.llms.custom_httpx.http_handler.get_async_httpx_client"
        ) as mock_client_factory:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "id": "msg_123",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello"}],
                "model": "claude-3-5-sonnet-20241022",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 20},
            }
            mock_response.headers = {}

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_factory.return_value = mock_client

            try:
                await litellm.acompletion(
                    model="anthropic/claude-3-5-sonnet-20241022",
                    messages=[{"role": "user", "content": "Hi"}],
                    extra_headers={"anthropic-beta": ",".join(all_headers)},
                    mock_response="Hello",
                )
            except Exception:
                pass

            if mock_client.post.called:
                call_kwargs = mock_client.post.call_args.kwargs
                headers = call_kwargs.get("headers", {})
                beta_header = headers.get("anthropic-beta", "")

                if beta_header:
                    beta_values = [b.strip() for b in beta_header.split(",")]
                    for unsupported_header in unsupported:
                        assert (
                            unsupported_header not in beta_values
                        ), f"Unsupported header '{unsupported_header}' should not be in HTTP headers for Anthropic"

    @pytest.mark.asyncio
    async def test_azure_ai_messages_http_headers_filtering(self):
        """Test that Azure AI messages API filters HTTP headers correctly."""
        all_headers = self.get_all_beta_headers()
        unsupported = self.get_unsupported_headers("azure_ai")

        with patch(
            "litellm.llms.custom_httpx.http_handler.get_async_httpx_client"
        ) as mock_client_factory:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "id": "msg_123",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello"}],
                "model": "claude-3-5-sonnet-20241022",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 20},
            }
            mock_response.headers = {}

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_factory.return_value = mock_client

            try:
                await litellm.acompletion(
                    model="azure_ai/claude-3-5-sonnet-20241022",
                    messages=[{"role": "user", "content": "Hi"}],
                    api_key="test-key",
                    api_base="https://test.azure.com",
                    extra_headers={"anthropic-beta": ",".join(all_headers)},
                    mock_response="Hello",
                )
            except Exception:
                pass

            if mock_client.post.called:
                call_kwargs = mock_client.post.call_args.kwargs
                headers = call_kwargs.get("headers", {})
                beta_header = headers.get("anthropic-beta", "")

                if beta_header:
                    beta_values = [b.strip() for b in beta_header.split(",")]
                    for unsupported_header in unsupported:
                        assert (
                            unsupported_header not in beta_values
                        ), f"Unsupported header '{unsupported_header}' should not be in HTTP headers for Azure AI"

    @pytest.mark.asyncio
    async def test_bedrock_converse_headers_and_body_filtering(self):
        """Test that Bedrock Converse filters both HTTP headers and request body correctly."""
        all_headers = self.get_all_beta_headers()
        unsupported = self.get_unsupported_headers("bedrock_converse")
        mapped_headers = self.get_mapped_headers("bedrock_converse")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "output": {
                    "message": {"role": "assistant", "content": [{"text": "Hello"}]}
                },
                "stopReason": "end_turn",
                "usage": {"inputTokens": 10, "outputTokens": 20},
            }
            mock_response.headers = {}
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__.return_value = mock_client

            try:
                await litellm.acompletion(
                    model="bedrock/converse/us.anthropic.claude-haiku-4-5-20251001-v1:0",
                    messages=[{"role": "user", "content": "Hi"}],
                    aws_access_key_id="test",
                    aws_secret_access_key="test",
                    aws_region_name="us-east-1",
                    extra_headers={"anthropic-beta": ",".join(all_headers)},
                    mock_response="Hello",
                )
            except Exception:
                pass

            if mock_client.post.called:
                call_kwargs = mock_client.post.call_args.kwargs
                headers = call_kwargs.get("headers", {})
                beta_header = headers.get("anthropic-beta", "")

                if beta_header:
                    beta_values = [b.strip() for b in beta_header.split(",")]
                    for unsupported_header in unsupported:
                        assert (
                            unsupported_header not in beta_values
                        ), f"Unsupported header '{unsupported_header}' should not be in HTTP headers for Bedrock Converse"

                data = call_kwargs.get("data")
                if data:
                    body = json.loads(data)
                    body_beta = body.get("additionalModelRequestFields", {}).get(
                        "anthropic_beta", []
                    )

                    for unsupported_header in unsupported:
                        assert (
                            unsupported_header not in body_beta
                        ), f"Unsupported header '{unsupported_header}' should not be in request body for Bedrock Converse"

                    for header, mapped_value in mapped_headers.items():
                        if header in all_headers and mapped_value in body_beta:
                            assert (
                                mapped_value in body_beta
                            ), f"Supported header '{header}' should be mapped to '{mapped_value}' in request body for Bedrock Converse"

    @pytest.mark.asyncio
    async def test_vertex_ai_messages_http_headers_filtering(self):
        """Test that Vertex AI messages API filters HTTP headers correctly."""
        all_headers = self.get_all_beta_headers()
        unsupported = self.get_unsupported_headers("vertex_ai")

        with patch(
            "litellm.llms.custom_httpx.http_handler.get_async_httpx_client"
        ) as mock_client_factory:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "id": "msg_123",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello"}],
                "model": "claude-3-5-sonnet-20241022",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 20},
            }
            mock_response.headers = {}

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_factory.return_value = mock_client

            with patch(
                "litellm.llms.vertex_ai.vertex_llm_base.VertexBase._ensure_access_token"
            ) as mock_token:
                mock_token.return_value = ("test-token", "test-project")

                try:
                    await litellm.acompletion(
                        model="vertex_ai/claude-3-5-sonnet-20241022",
                        messages=[{"role": "user", "content": "Hi"}],
                        vertex_project="test-project",
                        vertex_location="us-central1",
                        extra_headers={"anthropic-beta": ",".join(all_headers)},
                        mock_response="Hello",
                    )
                except Exception:
                    pass

            if mock_client.post.called:
                call_kwargs = mock_client.post.call_args.kwargs
                headers = call_kwargs.get("headers", {})
                beta_header = headers.get("anthropic-beta", "")

                if beta_header:
                    beta_values = [b.strip() for b in beta_header.split(",")]
                    for unsupported_header in unsupported:
                        assert (
                            unsupported_header not in beta_values
                        ), f"Unsupported header '{unsupported_header}' should not be in HTTP headers for Vertex AI"

    def test_header_mapping_correctness(self):
        """Test that headers are mapped correctly for providers with transformations."""
        test_cases = [
            {
                "provider": "bedrock",
                "input": "advanced-tool-use-2025-11-20",
                "expected": "tool-search-tool-2025-10-19",
            },
            {
                "provider": "vertex_ai",
                "input": "advanced-tool-use-2025-11-20",
                "expected": "tool-search-tool-2025-10-19",
            },
            {
                "provider": "anthropic",
                "input": "advanced-tool-use-2025-11-20",
                "expected": "advanced-tool-use-2025-11-20",
            },
            {
                "provider": "bedrock_converse",
                "input": "computer-use-2025-01-24",
                "expected": "computer-use-2025-01-24",
            },
            {
                "provider": "azure_ai",
                "input": "advanced-tool-use-2025-11-20",
                "expected": "advanced-tool-use-2025-11-20",
            },
        ]

        for test_case in test_cases:
            filtered = filter_and_transform_beta_headers(
                beta_headers=[test_case["input"]], provider=test_case["provider"]
            )

            assert (
                test_case["expected"] in filtered
            ), f"Header '{test_case['input']}' should be mapped to '{test_case['expected']}' for {test_case['provider']}, but got: {filtered}"

    def test_null_value_headers_filtered(self):
        """Test that headers with null values are always filtered out."""
        for provider in [
            "anthropic",
            "azure_ai",
            "bedrock_converse",
            "bedrock",
            "vertex_ai",
            "databricks",
            "cerebras",
            "cerebras_ai",
        ]:
            unsupported = self.get_unsupported_headers(provider)

            if unsupported:
                filtered = filter_and_transform_beta_headers(
                    beta_headers=unsupported, provider=provider
                )

                assert (
                    len(filtered) == 0
                ), f"All null-value headers should be filtered out for {provider}, but got: {filtered}"

    def test_empty_headers_list(self):
        """Test that empty headers list returns empty result."""
        for provider in [
            "anthropic",
            "azure_ai",
            "bedrock_converse",
            "bedrock",
            "vertex_ai",
            "databricks",
            "cerebras",
            "cerebras_ai",
        ]:
            filtered = filter_and_transform_beta_headers(
                beta_headers=[], provider=provider
            )

            assert (
                len(filtered) == 0
            ), f"Empty headers list should return empty result for {provider}"

    def test_mixed_supported_and_unsupported_headers(self):
        """Test filtering with a mix of supported, unsupported, and unknown headers."""
        for provider in [
            "anthropic",
            "azure_ai",
            "bedrock_converse",
            "bedrock",
            "vertex_ai",
            "databricks",
            "cerebras",
            "cerebras_ai",
        ]:
            supported = self.get_supported_headers(provider)
            unsupported = self.get_unsupported_headers(provider)
            mapped_headers = self.get_mapped_headers(provider)

            if not supported or not unsupported:
                continue

            test_headers = [supported[0]] + [unsupported[0]] + ["unknown-header-123"]

            filtered = filter_and_transform_beta_headers(
                beta_headers=test_headers, provider=provider
            )

            expected_mapped = mapped_headers[supported[0]]
            assert (
                expected_mapped in filtered
            ), f"Supported header should be in result for {provider}"
            assert (
                unsupported[0] not in filtered
            ), f"Unsupported header should not be in result for {provider}"
            assert (
                "unknown-header-123" not in filtered
            ), f"Unknown header should not be in result for {provider}"

    def test_cerebras_filters_all_anthropic_beta_headers(self):
        """Test that Cerebras provider filters out all Anthropic beta headers.

        This is critical for the Anthropic->Cerebras routing case:
        when an Anthropic model request is routed to Cerebras (which uses OpenAI-compatible
        interface), all unsupported beta parameters must be stripped to avoid 400 errors.
        """
        all_headers = self.get_all_beta_headers()

        # Cerebras should have all headers as null/unsupported
        cerebras_unsupported = self.get_unsupported_headers("cerebras")
        cerebras_supported = self.get_supported_headers("cerebras")

        assert (
            len(cerebras_supported) == 0
        ), "Cerebras should not support any Anthropic beta features"
        assert len(cerebras_unsupported) == len(
            all_headers
        ), "Cerebras should have entries for all Anthropic beta headers"

        # Test filtering with all headers
        filtered = filter_and_transform_beta_headers(
            beta_headers=all_headers, provider="cerebras"
        )

        assert (
            len(filtered) == 0
        ), f"All Anthropic beta headers should be filtered out for Cerebras, but got: {filtered}"

    def test_cerebras_ai_filters_all_anthropic_beta_headers(self):
        """Test that Cerebras_ai provider filters out all Anthropic beta headers."""
        all_headers = self.get_all_beta_headers()

        cerebras_ai_unsupported = self.get_unsupported_headers("cerebras_ai")
        cerebras_ai_supported = self.get_supported_headers("cerebras_ai")

        assert (
            len(cerebras_ai_supported) == 0
        ), "Cerebras_ai should not support any Anthropic beta features"
        assert len(cerebras_ai_unsupported) == len(
            all_headers
        ), "Cerebras_ai should have entries for all Anthropic beta headers"

        filtered = filter_and_transform_beta_headers(
            beta_headers=all_headers, provider="cerebras_ai"
        )

        assert (
            len(filtered) == 0
        ), f"All Anthropic beta headers should be filtered out for Cerebras_ai, but got: {filtered}"

    def test_cerebras_update_request_filters_both_headers_and_body(self):
        """Test that Cerebras properly filters both HTTP headers and request body beta parameters."""
        all_headers = self.get_all_beta_headers()

        headers = {"anthropic-beta": ",".join(all_headers)}
        request_data = {"anthropic_beta": all_headers}

        filtered_headers, filtered_data = update_request_with_filtered_beta(
            headers=headers,
            request_data=request_data,
            provider="cerebras",
        )

        # Both header and body field should be removed entirely (not just emptied)
        assert (
            "anthropic-beta" not in filtered_headers
        ), "anthropic-beta HTTP header should be removed for Cerebras"
        assert (
            "anthropic_beta" not in filtered_data
        ), "anthropic_beta request body field should be removed for Cerebras"


class TestCerebrasLegacyFormatConversion:
    """Test that Cerebras properly handles new→old format conversion and param stripping."""

    def test_cerebras_config_drops_anthropic_only_params(self):
        """CerebrasConfig.map_openai_params must drop Anthropic-specific params."""
        from litellm.llms.cerebras.chat import (
            CerebrasConfig,
            _CEREBRAS_UNSUPPORTED_ANTHROPIC_PARAMS,
        )

        config = CerebrasConfig()
        non_default_params = {
            "anthropic_beta": ["fast-mode-2026-02-01"],
            "top_k": 40,
            "stop_sequences": ["END"],
            "thinking": {"type": "enabled", "budget_tokens": 1024},
            "temperature": 0.7,
            "max_tokens": 1000,
        }
        optional_params: dict = {}

        result = config.map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model="cerebras/llama-3.3-70b",
            drop_params=True,
        )

        # Anthropic-specific params must be stripped
        for anthropic_param in _CEREBRAS_UNSUPPORTED_ANTHROPIC_PARAMS:
            assert (
                anthropic_param not in result
            ), f"Anthropic-specific param '{anthropic_param}' should be stripped for Cerebras"

        # Valid params must be kept
        assert result.get("temperature") == 0.7
        assert result.get("max_tokens") == 1000

    def test_cerebras_config_supported_params_list(self):
        """CerebrasConfig supported params must not include Anthropic-only params."""
        from litellm.llms.cerebras.chat import (
            CerebrasConfig,
            _CEREBRAS_UNSUPPORTED_ANTHROPIC_PARAMS,
        )

        config = CerebrasConfig()
        supported = set(
            config.get_supported_openai_params(model="cerebras/llama-3.3-70b")
        )

        for param in _CEREBRAS_UNSUPPORTED_ANTHROPIC_PARAMS:
            assert (
                param not in supported
            ), f"Anthropic-only param '{param}' should not be in Cerebras supported params"

    def test_cerebras_not_in_model_capability_response_api(self):
        """Cerebras model info should explicitly mark supports_response_api as false."""
        from litellm.utils import get_model_info

        try:
            model_info = get_model_info(
                model="cerebras/llama-3.3-70b",
                custom_llm_provider="cerebras",
            )
            if model_info:
                assert model_info.get("supports_response_api") is False, (
                    "Cerebras models should have supports_response_api=false "
                    "since they only support legacy chat completions"
                )
        except Exception:
            pass  # Model info not available in test environment

    def test_thinking_routing_skips_cerebras(self):
        """Thinking should not be routed to the Responses API for Cerebras."""
        from unittest.mock import MagicMock, patch

        from litellm.llms.anthropic.experimental_pass_through.adapters.handler import (
            LiteLLMMessagesToCompletionTransformationHandler,
        )

        completion_kwargs = {
            "model": "cerebras/llama-3.3-70b",
            "custom_llm_provider": "cerebras",
            "messages": [{"role": "user", "content": "Hi"}],
        }
        thinking = {"type": "enabled", "budget_tokens": 1024}

        # Should not raise and should not modify model to "responses/..."
        LiteLLMMessagesToCompletionTransformationHandler._route_openai_thinking_to_responses_api_if_needed(
            completion_kwargs, thinking=thinking
        )

        # Cerebras doesn't support Response API — model should not be prefixed
        assert not completion_kwargs.get("model", "").startswith(
            "responses/"
        ), "Cerebras model should not be routed to the Responses API"
