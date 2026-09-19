import os
from pathlib import Path

from ai.api.openai_completions import OpenAIProvider
from ai.registry import get_model, resolve_api_key
from coding.context import (
    discover_project_context,
    discover_skills,
    format_project_context,
    format_skills,
)
from coding.extensions.loader import load_extensions_from_dir
from coding.extensions.runtime import ExtensionRuntime
from coding.session import CodingSessionConfig
from coding.session_manager.manager import ChatSessionManager
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
    cwd: Path | None = None,
    chat_session_manager: ChatSessionManager | None = None,
) -> CodingSessionConfig:
    cwd = cwd or Path.cwd()

    if chat_session_manager is None:
        chat_session_manager = ChatSessionManager.new_session(cwd=cwd)

    context_files = discover_project_context(cwd)
    skills = discover_skills(cwd)
    dynamic_system_prompt: str = (
        DEFAULT_SYSTEM_PROMPT.strip()
        + format_project_context(context_files)
        + format_skills(skills)
    )

    tools = [
        create_bash_tool(),
        create_read_tool(),
        create_write_tool(),
        create_edit_tool(),
    ]

    extension_runtime = ExtensionRuntime()

    # Load default extension present in mini pi
    in_repo_bundled_dir = Path(__file__).parent.parent / "extensions"
    if in_repo_bundled_dir.is_dir():
        await load_extensions_from_dir(in_repo_bundled_dir, extension_runtime)

    # Load project local extensions
    extension_dir = cwd / ".mini-pi" / "extensions" / "bundled"
    extension_dir.mkdir(parents=True, exist_ok=True)

    await load_extensions_from_dir(extension_dir, extension_runtime)

    model_ref = os.getenv("MODEL")

    if not model_ref:
        raise ValueError(
            "MODEL environment variable is not set (expected provider:model_id)"
        )

    ai_model = get_model(model_ref)
    api_key = resolve_api_key(ai_model.provider)

    if not api_key:
        raise ValueError(f"API key is missing for provider: {ai_model.provider}")

    provider = OpenAIProvider(api_key=api_key, base_url=ai_model.base_url)

    config = CodingSessionConfig(
        provider=provider,
        model=ai_model,
        system=dynamic_system_prompt,
        tools=tools,
        chat_session_manager=chat_session_manager,
        auto_compact_threshold=50_000,
        extension_runtime=extension_runtime,
    )

    return config
