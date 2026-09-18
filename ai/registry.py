import os

from pydantic import BaseModel, Field

from ai.types import AIModel


class Provider(BaseModel):
    name: str
    api_key: str | None = None  # Literal Key or Environment Variable Name
    models: list[AIModel] = Field(default_factory=list)


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
