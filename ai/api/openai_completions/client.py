import asyncio
from collections.abc import AsyncIterator
import json

import httpx

from agent.cancellation import CancellationSignal
from agent.events import AgentEvent, DoneEvent
from agent.provider import ModelProvider
from agent.tools import AgentTool
from ai.types import AIModel, AgentMessage
from ai.api.openai_completions.parser import ChatStreamParser
from ai.api.openai_completions.serializer import build_chat_payload
from ai.provider_retry import abortable_sleep, calculate_retry_delay, is_retryable_error


class OpenAIProvider(ModelProvider):
    def __init__(self, api_key: str, base_url: str, max_retries: int = 3):
        self.api_key = api_key
        self.base_url = base_url
        self.timeout_seconds: int = 300
        self.max_retries = max_retries

    def _parse_sse_line(self, line: str) -> str | None:
        line = line.strip()
        if not line or not line.startswith("data:"):
            return
        return line.removeprefix("data:").strip()

    def stream_response(
        self,
        model: AIModel,
        system: str,
        messages: list[AgentMessage],
        tools: list[AgentTool],
        signal: CancellationSignal | None = None,
    ) -> AsyncIterator[AgentEvent]:
        payload = build_chat_payload(model, system, messages, tools)

        headers = {"Authorization": f"Bearer {self.api_key}"}

        async def _run():
            attempt = 0
            while True:
                has_yielded_event = False
                parser = ChatStreamParser()

                if signal is not None and signal.is_cancelled():
                    yield DoneEvent(
                        message=parser.build_assistant_message(
                            stop_reason="aborted",
                        )
                    )

                    return

                try:
                    # TODO
                    if not self.api_key:
                        raise ValueError(
                            f"API key is not set for provider: {model.provider}"
                        )

                    async with httpx.AsyncClient(
                        timeout=self.timeout_seconds
                    ) as client:
                        async with client.stream(
                            "POST",
                            f"{self.base_url}/chat/completions",
                            json=payload,
                            headers=headers,
                        ) as response:
                            if response.status_code >= 400:
                                body = await response.aread()
                                body_text = body.decode(errors="replace")
                                response_headers = dict(response.headers)

                                if attempt < self.max_retries and is_retryable_error(
                                    status_code=response.status_code,
                                    response_headers=response_headers,
                                ):
                                    try:
                                        delay = calculate_retry_delay(
                                            attempt=attempt,
                                            response_headers=response_headers,
                                        )
                                    except ValueError as verr:
                                        yield DoneEvent(
                                            message=parser.build_assistant_message(
                                                stop_reason="error",
                                                error_message=f"{body_text} ({verr})",
                                            )
                                        )
                                        return

                                    attempt += 1
                                    is_aborted = not (
                                        await abortable_sleep(delay, signal)
                                    )
                                    if is_aborted:
                                        yield DoneEvent(
                                            message=parser.build_assistant_message(
                                                stop_reason="aborted",
                                            )
                                        )
                                        return

                                    continue

                                yield DoneEvent(
                                    message=parser.build_assistant_message(
                                        stop_reason="error",
                                        error_message=body_text,
                                    )
                                )
                                return

                            async for line in response.aiter_lines():
                                if signal is not None and signal.is_cancelled():
                                    yield DoneEvent(
                                        message=parser.build_assistant_message(
                                            stop_reason="aborted",
                                        )
                                    )

                                    return

                                data = self._parse_sse_line(line)

                                if data is None:
                                    continue

                                if data == "[DONE]":
                                    break

                                chunk = json.loads(data)
                                events = parser.feed(chunk)

                                for e in events:
                                    has_yielded_event = True
                                    yield e

                    yield parser.finalize()
                    return
                except Exception as err:
                    if (
                        not has_yielded_event
                        and attempt < self.max_retries
                        and is_retryable_error(error=err)
                    ):
                        try:
                            delay = calculate_retry_delay(
                                attempt=attempt,
                            )
                        except ValueError as verr:
                            yield DoneEvent(
                                message=parser.build_assistant_message(
                                    stop_reason="error",
                                    error_message=f"{err} ({verr})",
                                )
                            )
                            return

                        attempt += 1
                        is_aborted = not (await abortable_sleep(delay, signal))
                        if is_aborted:
                            yield DoneEvent(
                                message=parser.build_assistant_message(
                                    stop_reason="aborted",
                                )
                            )
                            return

                        continue

                    yield DoneEvent(
                        message=parser.build_assistant_message(
                            stop_reason="error",
                            error_message=str(err),
                        )
                    )
                    return

        return _run()
