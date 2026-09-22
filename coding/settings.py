from pathlib import Path

from pydantic import BaseModel

SETTINGS_FILE_PATH = Path.home() / ".mini-pi" / "settings.json"


class Settings(BaseModel):
    default_model_ref: str | None = None


def load_settings() -> Settings:
    if not SETTINGS_FILE_PATH.is_file():
        return Settings()

    try:
        content = SETTINGS_FILE_PATH.read_text(encoding="utf-8")
        return Settings.model_validate_json(content)
    except Exception:
        return Settings()


def set_default_model(model_ref: str) -> None:
    settings = load_settings()
    settings.default_model_ref = model_ref
    SETTINGS_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE_PATH.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
