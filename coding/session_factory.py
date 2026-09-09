import os
from pathlib import Path

from agent.session.storage import SessionStorage
from ai.openai import OpenAIProvider
from coding.chat_session_manager import ChatSessionManager
from coding.context import (
    discover_project_context,
    discover_skills,
    format_project_context,
    format_skills,
)
from coding.extensions.loader import load_extensions_from_dir
from coding.extensions.runtime import ExtensionRuntime
from coding.session import CodingSessionConfig
from coding.tools import (
    create_edit_tool,
    create_read_tool,
    create_bash_tool,
    create_write_tool,
)

DEFAULT_SYSTEM_PROMPT = """
You are helpful assistant. You have access to user filesystem.
"""


async def build_session_config(
    cwd: Path | None = None, storage: SessionStorage | None = None
) -> CodingSessionConfig:
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("MODEL")

    cwd = cwd or Path.cwd()

    context_files = discover_project_context(cwd)
    skills = discover_skills(cwd)
    dynamic_system_prompt: str = (
        DEFAULT_SYSTEM_PROMPT.strip()
        + format_project_context(context_files)
        + format_skills(skills)
    )

    provider = OpenAIProvider(api_key=api_key, base_url=base_url)

    tools = [
        create_bash_tool(),
        create_read_tool(),
        create_write_tool(),
        create_edit_tool(),
    ]

    extension_runtime = ExtensionRuntime()
    extension_dir = cwd / ".mini-pi" / "extensions"
    extension_dir.mkdir(parents=True, exist_ok=True)

    await load_extensions_from_dir(extension_dir, extension_runtime)

    config = CodingSessionConfig(
        provider=provider,
        model=model,
        system=dynamic_system_prompt,
        tools=tools,
        storage=storage,
        auto_compact_threshold=50_000,
        extension_runtime=extension_runtime,
    )

    return config
