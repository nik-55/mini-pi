# Reference: https://github.com/openai/openai-python/blob/v3.13.0/src/openai/_base_client.py


import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import random
from typing import Any

import httpx

from agent.cancellation import CancellationSignal

# 4xx class means Client error: the request itself is wrong
# 400 Bad request = json payload or invalid parameters
# 401 = invalid api key
# 402 = payment required
# Try on above 4xx will fail always as it represent client error
# The following three 4xx class though can be retried as it represent condition where waiting and
# sending the exact same request can be succeed
RETRYABLE_STATUS_CODES = {
    408,  # Request timeouts
    409,  # Lock timeouts
    429,  # Rate limits,
}

DEFAULT_MAX_RETRY_DELAY_SECONDS = 60.0


async def abortable_sleep(
    seconds: float, signal: CancellationSignal | None = None
) -> bool:
    # Sleep for 'seconds' or until signal is cancelled
    # True if slept full duration

    if signal is None:
        await asyncio.sleep(seconds)
        return True

    try:
        await asyncio.wait_for(signal.wait(), timeout=seconds)
        return False
    except TimeoutError:
        return True


def normalize_headers(headers: dict[str, Any]) -> dict[str, Any]:
    return {
        k.lower(): (v.strip().lower() if isinstance(v, str) else v)
        for k, v in headers.items()
    }


def is_retryable_error(
    status_code: int | None = None,
    response_headers: dict[str, str] | None = None,
    error: Exception | None = None,
) -> bool:
    if response_headers:
        response_headers = normalize_headers(response_headers)

        # Not a standard header
        should_retry = response_headers.get("x-should-retry")

        if should_retry == "true":
            return True
        elif should_retry == "false":
            return False

    if status_code is not None:
        if status_code in RETRYABLE_STATUS_CODES or status_code >= 500:
            return True
        return False

    if error is not None:
        # Network errors (connection reset, DNS failure, timeouts)
        if isinstance(error, httpx.TransportError):
            return True

    return False


def _parse_retry_after_header(value: str) -> float | None:
    val = value.strip()

    try:
        return float(val)  # seconds
    except ValueError:
        pass

    try:
        date = parsedate_to_datetime(val)
        delay = (date - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delay)  # if negative delay then u can retry immediately
    except Exception:
        pass


def calculate_retry_delay(
    attempt: int,
    response_headers: dict[str, str] | None = None,
    max_delay: float = DEFAULT_MAX_RETRY_DELAY_SECONDS,
):
    if response_headers:
        response_headers = normalize_headers(response_headers)

        server_delay: float | None = None

        if "retry-after-ms" in response_headers:
            try:
                server_delay = float(response_headers["retry-after-ms"]) / 1000.0
            except ValueError:
                pass

        if server_delay is None and "retry-after" in response_headers:
            server_delay = _parse_retry_after_header(response_headers["retry-after"])

        if server_delay is not None:
            if server_delay > max_delay:
                raise ValueError(
                    f"Server requested {server_delay}s retry delay (exceeds {max_delay}s cap)"
                )

            return server_delay

    # exponential backoff with jitter
    base = 1
    # 1 sec, 2 sec, 4 sec, 8 sec ...
    base_delay = min(base * (2**attempt), max_delay)
    jitter = 1.0 - (random.random() * 0.25)  # 0.75 - 1.0

    # we are giving server at least 75% of base delay always
    return base_delay * jitter
