"""
Cerebras Chat Completions API

Cerebras uses an OpenAI-compatible interface but only supports the legacy
chat completions format (/v1/chat/completions). It does NOT support:
  - OpenAI Responses API (/v1/responses)
  - Newer OpenAI chat completion params (store, metadata, etc.)
  - Anthropic-specific params (top_k, stop_sequences, thinking, etc.)

When routing newer-format requests through Cerebras, LiteLLM uses
LiteLLMCompletionTransformationHandler to downgrade the request to the
legacy chat completions format and upgrade the response back to the
expected format.
"""

from typing import Optional, Set

from litellm.llms.openai.chat.gpt_transformation import OpenAIGPTConfig
from litellm.utils import supports_reasoning

# Anthropic-specific params that must never be forwarded to Cerebras.
# These are stripped by map_openai_params() since they're not in the
# supported list, but this set is here for documentation and explicit
# handling if the params ever arrive via a different code path.
_CEREBRAS_UNSUPPORTED_ANTHROPIC_PARAMS: Set[str] = {
    "anthropic_beta",
    "top_k",
    "stop_sequences",
    "thinking",
}


class CerebrasConfig(OpenAIGPTConfig):
    """
    Reference: https://inference-docs.cerebras.ai/api-reference/chat-completions

    Cerebras supports legacy OpenAI chat completions only. Unsupported params
    are silently dropped by map_openai_params(); the Responses API path is
    handled via LiteLLMCompletionTransformationHandler (see responses/main.py).
    """

    max_tokens: Optional[int] = None
    response_format: Optional[dict] = None
    seed: Optional[int] = None
    stream: Optional[bool] = None
    top_p: Optional[int] = None
    tool_choice: Optional[str] = None
    tools: Optional[list] = None
    user: Optional[str] = None
    reasoning_effort: Optional[str] = None

    def __init__(
        self,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
        seed: Optional[int] = None,
        stop: Optional[str] = None,
        stream: Optional[bool] = None,
        temperature: Optional[float] = None,
        top_p: Optional[int] = None,
        tool_choice: Optional[str] = None,
        tools: Optional[list] = None,
        user: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
    ) -> None:
        locals_ = locals().copy()
        for key, value in locals_.items():
            if key != "self" and value is not None:
                setattr(self.__class__, key, value)

    @classmethod
    def get_config(cls):
        return super().get_config()

    def get_supported_openai_params(self, model: str) -> list:
        """
        Get the supported OpenAI params for the given model

        """

        supported_params = [
            "max_tokens",
            "max_completion_tokens",
            "response_format",
            "seed",
            "stop",
            "stream",
            "temperature",
            "top_p",
            "tool_choice",
            "tools",
            "user",
        ]

        # Only add reasoning_effort for models that support it
        if supports_reasoning(model=model, custom_llm_provider="cerebras"):
            supported_params.append("reasoning_effort")

        return supported_params

    def map_openai_params(
        self,
        non_default_params: dict,
        optional_params: dict,
        model: str,
        drop_params: bool,
    ) -> dict:
        supported_openai_params = self.get_supported_openai_params(model=model)
        for param, value in non_default_params.items():
            if param in _CEREBRAS_UNSUPPORTED_ANTHROPIC_PARAMS:
                # Explicitly drop Anthropic-specific params that should never
                # reach Cerebras's OpenAI-compatible endpoint.
                continue
            elif param == "max_completion_tokens":
                optional_params["max_tokens"] = value
            elif param in supported_openai_params:
                optional_params[param] = value
        return optional_params
