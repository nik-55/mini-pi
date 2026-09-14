import asyncio
from collections.abc import AsyncIterator
import json

import httpx

from agent.events import AssistantErrorEvent, AgentEvent
from agent.messages import AgentMessage
from agent.provider import ModelProvider
from agent.tools import AgentTool
from ai.parser import ChatStreamParser
from ai.retry import calculate_retry_delay, is_retryable_error
from ai.serializer import build_chat_payload


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
        model: str,
        system: str,
        messages: list[AgentMessage],
        tools: list[AgentTool],
    ) -> AsyncIterator[AgentEvent]:
        payload = build_chat_payload(model, system, messages, tools)

        headers = {"Authorization": f"Bearer {self.api_key}"}

        async def _run():
            attempt = 0
            while True:
                has_yielded_event = False
                parser = ChatStreamParser()

                try:
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
                                        yield AssistantErrorEvent(
                                            error=f"{body_text} ({verr})"
                                        )
                                        return

                                    attempt += 1
                                    await asyncio.sleep(delay)
                                    continue

                                yield AssistantErrorEvent(error=body_text)
                                return

                            async for line in response.aiter_lines():
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
                            yield AssistantErrorEvent(error=f"{err} ({verr})")
                            return

                        attempt += 1
                        await asyncio.sleep(delay)
                        continue

                    yield AssistantErrorEvent(error=str(err))
                    return

        return _run()
