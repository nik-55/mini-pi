from collections import deque

from pydantic import Field, BaseModel

from agent.messages import UserMessage


# Snapshot of Queued Messages
class QueueMessages(BaseModel):
    steering: tuple[UserMessage, ...] = Field(default_factory=tuple)
    follow_up: tuple[UserMessage, ...] = Field(default_factory=tuple)

    @property
    def count(self) -> int:
        return len(self.steering) + len(self.follow_up)


class MessageQueueHandler:
    def __init__(self):
        self._steering_queue: deque[UserMessage] = deque()
        self._follow_up_queue: deque[UserMessage] = deque()

    @property
    def snapshot(self) -> QueueMessages:
        return QueueMessages(
            steering=tuple(self._steering_queue),
            follow_up=tuple(self._follow_up_queue),
        )

    @property
    def pending_count(self) -> int:
        return len(self._steering_queue) + len(self._follow_up_queue)

    def steer(self, msg: str) -> QueueMessages:
        self._steering_queue.append(UserMessage(content=msg))
        return self.snapshot

    def follow_up(self, msg: str) -> QueueMessages:
        self._follow_up_queue.append(UserMessage(content=msg))
        return self.snapshot

    def clear(self) -> QueueMessages:
        current = self.snapshot
        self._steering_queue.clear()
        self._follow_up_queue.clear()
        return current

    def drain_steering(self) -> tuple[UserMessage, ...]:
        return self._drain(self._steering_queue)

    def drain_follow_up(self) -> tuple[UserMessage, ...]:
        return self._drain(self._follow_up_queue)

    def _drain(self, queue: deque[UserMessage]) -> tuple[UserMessage, ...]:
        if not queue:
            return tuple()

        msgs = tuple(queue)
        queue.clear()
        return msgs
