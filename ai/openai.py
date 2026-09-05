from collections.abc import AsyncIterator
import json

import httpx

from agent.events import AssistantErrorEvent, AgentEvent
from agent.messages import AgentMessage
from agent.provider import ModelProvider
from agent.tools import AgentTool
from ai.parser import ChatStreamParser
from ai.serializer import build_chat_payload


class OpenAIProvider(ModelProvider):
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url
        self.timeout_seconds: int = 300

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
        parser = ChatStreamParser()

        payload = build_chat_payload(model, system, messages, tools)

        headers = {"Authorization": f"Bearer {self.api_key}"}

        async def _run():
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    ) as response:
                        if response.status_code >= 400:
                            body = await response.aread()
                            body_text = body.decode(errors="replace")
                            yield AssistantErrorEvent(error=body_text)
                            return

                        async for line in response.aiter_lines():
                            data = self._parse_sse_line(line)

                            if data is None:
                                continue

                            if data == "[DONE]":
                                break

                            try:
                                chunk = json.loads(data)
                                events = parser.feed(chunk)

                                for e in events:
                                    yield e
                            except Exception:
                                continue

                yield parser.finalize()
            except httpx.HTTPError as err:
                yield AssistantErrorEvent(error=str(err))

        return _run()
