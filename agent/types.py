from ai.types import Message

type AgentMessage[CustomMessage] = Message | CustomMessage
