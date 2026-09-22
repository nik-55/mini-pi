# Messages specific to coding layer
# AI layer dont need to know about this messages

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from ai.types import AgentMessage, UserMessage


class CompactionSummaryMessage(BaseModel):
    role: Literal["compaction_summary"] = "compaction_summary"
    summary: str


SessionMessage = Annotated[
    AgentMessage | CompactionSummaryMessage,
    Field(discriminator="role"),
]


# Convert Session messages to AI layer compatible messages
def convert_message_to_llm_compatible(messages: list[SessionMessage]) -> list[AgentMessage]:
    results: list[AgentMessage] = []

    for m in messages:
        if isinstance(m, CompactionSummaryMessage):
            results.append(
                UserMessage(
                    content=(
                        "The conversation history before this point was compacted into the "
                        f"following summary:\n<summary>\n{m.summary}\n</summary>"
                    )
                )
            )
        else:
            results.append(m)

    return results
