from pathlib import Path

from pydantic import RootModel

AUTH_FILE_PATH = Path.home() / ".mini-pi" / "auth.json"


# [<provider_name>, <api_key>]
class AuthStorage(RootModel[dict[str, str]]):
    root: dict[str, str] = {}


def _load_auth_storage() -> AuthStorage:
    if not AUTH_FILE_PATH.is_file():
        return AuthStorage(root={})

    try:
        content = AUTH_FILE_PATH.read_text(encoding="utf-8")
        return AuthStorage.model_validate_json(content)
    except Exception:
        # return default so user can login again
        # which will rewrite the broken file
        return AuthStorage(root={})


def _save_auth_storage(storage: AuthStorage) -> None:
    AUTH_FILE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,  # Octal (base 8) integer
    )
    AUTH_FILE_PATH.write_text(storage.model_dump_json(indent=2), encoding="utf-8")


def get_api_key_from_auth(provider: str) -> str | None:
    storage = _load_auth_storage()
    cred = storage.root.get(provider)

    if cred and cred.strip():
        return cred.strip()

    return


def set_api_key_to_auth(provider: str, key: str) -> None:
    storage = _load_auth_storage()
    storage.root[provider] = key
    _save_auth_storage(storage)


def remove_api_key_from_auth(provider: str) -> bool:
    storage = _load_auth_storage()
    if provider in storage.root:
        del storage.root[provider]
        _save_auth_storage(storage)
        return True
    return False
