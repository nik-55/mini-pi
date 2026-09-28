from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field, replace
import os

from ai.provider import StreamFunction
from ai.types import AIModel, Context, StreamEvent, StreamOptions


@dataclass
class Provider:
    name: str
    api_key: str | None = None  # Literal Key or Environment Variable Name
    models: list[AIModel] = field(default_factory=list)
    # api name -> stream function
    # A single provider often support multiple API implementations
    # Fireworks provide API with both anthropic and openai compatibiliy
    # eg: {"openai-completions": stream_openai_completions}
    streams: dict[str, StreamFunction] = field(default_factory=dict)


_PROVIDERS: dict[str, Provider] = {}


def register_inference_provider(provider: Provider):
    if provider.name in _PROVIDERS:
        raise ValueError(f"{provider.name} already exist")

    _PROVIDERS[provider.name] = provider


def get_model(model_ref: str) -> AIModel:
    provider_name, model_id = model_ref.split(":", 1)  # provider:model_id

    if None in [provider_name, model_id]:
        raise ValueError(f"provider and model id can not be none")

    if provider_name not in _PROVIDERS:
        raise ValueError(f"{provider_name} provider not found")

    for m in _PROVIDERS[provider_name].models:
        if m.id == model_id:
            return m

    raise ValueError(f"{model_id} not found with provider {provider_name}")


def list_models() -> list[AIModel]:
    models = []
    for provider in _PROVIDERS.values():
        models.extend(provider.models)

    return models


def resolve_api_key(provider_name: str) -> str | None:
    if provider_name not in _PROVIDERS:
        raise ValueError(f"{provider_name} provider not found")

    provider = _PROVIDERS[provider_name]

    if provider.api_key is None:
        return

    if provider.api_key.startswith("$"):
        return os.environ.get(provider.api_key[1:])

    return provider.api_key


CredentialReader = Callable[[str], str | None]

_CREDENTIAL_READER: CredentialReader | None = None


def set_credential_reader(reader: CredentialReader) -> None:
    global _CREDENTIAL_READER
    _CREDENTIAL_READER = reader


def get_api_key(provider: str) -> str | None:
    return (
        _CREDENTIAL_READER(provider) if _CREDENTIAL_READER else None
    ) or resolve_api_key(provider)


def stream(
    model: AIModel,
    context: Context,
    options: StreamOptions,
) -> AsyncIterator[StreamEvent]:
    provider = _PROVIDERS.get(model.provider)

    if provider is None:
        raise ValueError(f"Unknown provider: {model.provider}")

    fn = provider.streams.get(model.api)

    if fn is None:
        raise ValueError(
            f"Provider {model.provider} has no API implementation for {model.api}"
        )

    api_key = options.api_key or get_api_key(model.provider)

    # Create copy before modifying
    options = replace(options, api_key=api_key)

    return fn(
        model,
        context,
        options,
    )
