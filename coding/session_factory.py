import os
from pathlib import Path

from ai.registry import get_model, list_models, set_credential_reader
from coding.auth import get_api_key_from_auth
from coding.context import (
    discover_project_context,
    discover_skills,
    format_project_context,
    format_skills,
)
from coding.extensions.types import ExtensionContext
from coding.extensions.loader import load_extensions_from_dir
from coding.extensions.runtime import ExtensionRuntime
from coding.session import CodingSessionConfig
from coding.session_manager.manager import ChatSessionManager
from coding.settings import load_settings
from coding.tools import (
    create_edit_tool,
    create_read_tool,
    create_bash_tool,
    create_write_tool,
)
from coding.compaction.types import CompactionSettings

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
        create_bash_tool(str(cwd)),
        create_read_tool(str(cwd)),
        create_write_tool(str(cwd)),
        create_edit_tool(str(cwd)),
    ]

    extension_runtime = ExtensionRuntime(context=ExtensionContext(cwd=cwd))

    # Load default extension present in mini pi
    in_repo_bundled_dir = Path(__file__).parent.parent / "extensions"
    if in_repo_bundled_dir.is_dir():
        await load_extensions_from_dir(in_repo_bundled_dir, extension_runtime)

    # Load project local extensions
    extension_dir = cwd / ".mini-pi" / "extensions" / "bundled"
    extension_dir.mkdir(parents=True, exist_ok=True)

    await load_extensions_from_dir(extension_dir, extension_runtime)

    # Precedence order: auth storage / settings > environment variable
    settings = load_settings()
    model_ref = settings.default_model_ref or os.getenv("MODEL")

    if not model_ref:
        available_models = list_models()
        if available_models:
            first = available_models[0]
            model_ref = f"{first.provider}:{first.id}"
        else:
            raise ValueError("No model registered.")

    ai_model = get_model(model_ref)
    set_credential_reader(get_api_key_from_auth)

    config = CodingSessionConfig(
        model=ai_model,
        system=dynamic_system_prompt,
        tools=tools,
        chat_session_manager=chat_session_manager,
        compaction_settings=CompactionSettings(),  # use default
        extension_runtime=extension_runtime,
    )

    return config
