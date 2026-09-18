from ai.registry import Provider
from ai.types import AIModel, OpenAICompletionsComp
from coding.extensions.api import ExtensionAPI


def setup(api: ExtensionAPI) -> None:
    base_url = "https://api.fireworks.ai/inference/v1"
    provider_api = "openai-completions"
    provider_name = "fireworks"

    # TODO: Require confirming the configuration
    api.register_llm_provider(
        provider=Provider(
            name=provider_name,
            api_key="$FIREWORKS_API_KEY",
            models=[
                # https://fireworks.ai/models/fireworks/minimax-m3
                # https://platform.minimax.io/docs/api-reference/text-chat-openai#body-thinking
                # It requires thinking: {"type": "adaptive" or "disabled"}
                # default when thinking omitted is adaptive
                AIModel(
                    id="accounts/fireworks/models/minimax-m3",
                    name="Minimax M3",
                    api=provider_api,
                    provider=provider_name,
                    base_url=base_url,
                    reasoning=True,
                    context_window=512_000,
                    max_tokens=64_000,
                    compat=OpenAICompletionsComp(
                        supports_usage_in_streaming=True,
                        max_tokens_field="max_tokens",
                    ),
                ),
            ],
        )
    )
