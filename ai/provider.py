from collections.abc import AsyncIterator, Callable

from ai.types import AIModel, Context, StreamEvent, StreamOptions

StreamFunction = Callable[
    [
        AIModel,
        Context,
        StreamOptions,
    ],
    AsyncIterator[StreamEvent],
]
