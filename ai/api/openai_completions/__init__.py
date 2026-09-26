# OpenAI represent Chat completion API /v1/chat/completions
# https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
# https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events

from ai.api.openai_completions.client import stream_openai_completions

__all__ = ["stream_openai_completions"]
