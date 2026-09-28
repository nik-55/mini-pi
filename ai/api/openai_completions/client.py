from collections.abc import AsyncIterator
import json

import httpx

from ai.types import (
    Context,
    DoneEvent,
    StreamEvent,
    StreamOptions,
    AIModel,
)
from ai.api.openai_completions.parser import ChatStreamParser
from ai.api.openai_completions.serializer import build_chat_payload
from ai.provider_retry import abortable_sleep, calculate_retry_delay, is_retryable_error


def _parse_sse_line(line: str) -> str | None:
    line = line.strip()
    if not line or not line.startswith("data:"):
        return
    return line.removeprefix("data:").strip()


def stream_openai_completions(
    model: AIModel,
    context: Context,
    options: StreamOptions,
) -> AsyncIterator[StreamEvent]:
    payload = build_chat_payload(model, context.system, context.messages, context.tools)

    headers = {"Authorization": f"Bearer {options.api_key}"}

    async def _run():
        attempt = 0
        while True:
            has_yielded_event = False
            parser = ChatStreamParser()

            if options.signal is not None and options.signal.is_cancelled():
                yield DoneEvent(
                    message=parser.build_assistant_message(
                        stop_reason="aborted",
                    )
                )

                return

            try:
                # TODO
                if not options.api_key:
                    raise ValueError(
                        f"API key is not set for provider: {model.provider}"
                    )

                async with httpx.AsyncClient(timeout=options.timeout_seconds) as client:
                    async with client.stream(
                        "POST",
                        f"{model.base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    ) as response:
                        if response.status_code >= 400:
                            body = await response.aread()
                            body_text = body.decode(errors="replace")
                            response_headers = dict(response.headers)

                            if attempt < options.max_retries and is_retryable_error(
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
                                    await abortable_sleep(delay, options.signal)
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
                            if (
                                options.signal is not None
                                and options.signal.is_cancelled()
                            ):
                                yield DoneEvent(
                                    message=parser.build_assistant_message(
                                        stop_reason="aborted",
                                    )
                                )

                                return

                            data = _parse_sse_line(line)

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
                    and attempt < options.max_retries
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
                    is_aborted = not (await abortable_sleep(delay, options.signal))
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
