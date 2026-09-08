from __future__ import annotations

from types import SimpleNamespace

import pytest

from gcp_observability_agent.infrastructure.llm.gemini import (
    GeminiLLMConfig,
    GeminiLLMProvider,
    GeminiProviderError,
    GeminiTimeoutError,
)


class FakeModels:
    def __init__(self, responses) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeClient:
    def __init__(self, responses) -> None:
        self.models = FakeModels(responses)


def _response(name="search_metric_descriptors", args=None, usage=None):
    return SimpleNamespace(
        function_calls=[SimpleNamespace(name=name, args=args if args is not None else {"query": "cpu"})],
        usage_metadata=usage,
    )


def test_gemini_provider_translates_registered_function_call_and_extracts_usage() -> None:
    usage = SimpleNamespace(
        prompt_token_count=12,
        candidates_token_count=8,
        total_token_count=20,
        cached_content_token_count=3,
    )
    client = FakeClient([_response(usage=usage)])
    provider = GeminiLLMProvider(GeminiLLMConfig(model="gemini-test", temperature=0.2), client=client)

    action = provider.next_action({"investigation": {"question": "What happened?"}})
    request = client.models.calls[0]
    config = request["config"].model_dump(by_alias=True)

    assert action.tool_name.value == "search_metric_descriptors"
    assert action.arguments == {"query": "cpu"}
    assert request["model"] == "gemini-test"
    assert config["temperature"] == 0.2
    assert config["automaticFunctionCalling"]["disable"] is True
    declarations = config["tools"][0]["functionDeclarations"]
    assert {declaration["name"] for declaration in declarations} == {
        "search_metric_descriptors", "query_metric", "list_resources", "get_alerts", "conclude_investigation",
    }
    assert provider.last_usage is not None
    assert provider.last_usage.total_tokens == 20
    assert provider.last_usage.cached_input_tokens == 3


@pytest.mark.parametrize(
    "response, message",
    [
        (SimpleNamespace(function_calls=[]), "exactly one"),
        (SimpleNamespace(function_calls=[SimpleNamespace(name="shell", args={})]), "unregistered"),
        (SimpleNamespace(function_calls=[SimpleNamespace(name="query_metric", args="not-an-object")]), "arguments"),
    ],
)
def test_gemini_provider_rejects_malformed_or_unregistered_function_calls(response, message) -> None:
    provider = GeminiLLMProvider(client=FakeClient([response]))

    with pytest.raises(GeminiProviderError, match=message):
        provider.next_action({})


def test_gemini_provider_retries_timeout_then_returns_a_structured_action() -> None:
    client = FakeClient([TimeoutError(), _response()])
    provider = GeminiLLMProvider(GeminiLLMConfig(max_retries=1), client=client)

    action = provider.next_action({})

    assert action.tool_name.value == "search_metric_descriptors"
    assert len(client.models.calls) == 2


def test_gemini_provider_retries_rate_limit_but_exposes_only_safe_errors() -> None:
    class RateLimitError(Exception):
        status_code = 429

    client = FakeClient([RateLimitError("api key=secret"), _response()])
    provider = GeminiLLMProvider(GeminiLLMConfig(max_retries=1), client=client)

    assert provider.next_action({}).tool_name.value == "search_metric_descriptors"
    assert len(client.models.calls) == 2

    failed = GeminiLLMProvider(client=FakeClient([RuntimeError("api key=secret")]))
    with pytest.raises(GeminiProviderError, match="Gemini request failed") as error:
        failed.next_action({})
    assert "secret" not in str(error.value)


def test_gemini_provider_raises_timeout_after_bounded_retries() -> None:
    provider = GeminiLLMProvider(GeminiLLMConfig(max_retries=1), client=FakeClient([TimeoutError(), TimeoutError()]))

    with pytest.raises(GeminiTimeoutError):
        provider.next_action({})


def test_tool_schemas_are_complete_and_provider_neutral() -> None:
    schemas = GeminiLLMProvider.tool_schemas()

    assert len(schemas) == 5
    assert all(schema["parameters_json_schema"]["type"] == "object" for schema in schemas)
    assert all("google" not in repr(schema).lower() for schema in schemas)
