import importlib.util
import inspect
from pathlib import Path
import sys

from coding.extensions.api import ExtensionAPI
from coding.extensions.runtime import ExtensionRuntime


async def load_extension_from_file(
    path: Path, runtime: ExtensionRuntime
) -> ExtensionAPI | None:
    # General pattern for how we dynamically import python files
    # for eg from plugin directory
    # spec --> module --> exec_module

    module_name = f"mini_pi_ext_{path.stem}"

    spec = importlib.util.spec_from_file_location(module_name, path)

    if spec is None or spec.loader is None:
        return

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        print(f"[Warning] Failed to import extension {path.name}: {exc}", flush=True)
        return

    setup_fn = getattr(module, "setup", None)

    extension_api = ExtensionAPI(path.stem)
    try:
        res = setup_fn(extension_api)
        if inspect.isawaitable(res):
            await res

    except Exception as exc:
        print(f"[Warning] Failed to import extension {path.name}: {exc}", flush=True)
        return

    runtime.register_extension(extension_api)
    return extension_api


async def load_extensions_from_dir(
    directory: Path, runtime: ExtensionRuntime
) -> list[ExtensionAPI]:
    if not directory.is_dir():
        return []

    loaded: list[ExtensionAPI] = []

    for path in sorted(directory.iterdir(), key=lambda p: p.name):
        if path.is_file() and path.suffix == ".py":
            api = await load_extension_from_file(path, runtime)

            if api is not None:
                loaded.append(api)

    return loaded
