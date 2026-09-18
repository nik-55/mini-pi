from typing import Any
import jsonschema


def validate_tool_arguments(schema: dict[str, Any], arguments: Any) -> None:
    if not isinstance(arguments, dict):
        raise ValueError(
            f"Arguments must be dictionary, got {type(arguments).__name__}"
        )

    if "_raw_arguments" in arguments:
        raise ValueError(
            f"Failed to parse tool call arguments as valid json: {arguments['_raw_arguments']}"
        )

    try:
        jsonschema.validate(instance=arguments, schema=schema)
    except jsonschema.ValidationError as err:
        key_path = ".".join(str(p) for p in err.absolute_path) or "root"
        raise ValueError(f"Validation failed at '{key_path}': {err.message}") from err
