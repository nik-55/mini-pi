from pydantic import TypeAdapter

from agent.session.entries import SessionEntry

session_entry_adapter: TypeAdapter[SessionEntry] = TypeAdapter(SessionEntry)


class SessionJsonlError(ValueError):
    pass


def entry_to_json_line(entry: SessionEntry) -> str:
    return session_entry_adapter.dump_json(entry).decode() + "\n"


def entry_from_json_line(line: str) -> SessionEntry:
    try:
        return session_entry_adapter.validate_json(line)
    except Exception as exc:
        raise SessionJsonlError(f"Invalid session entry: {exc}")


def entries_from_json_lines(lines: list[str]) -> list[SessionEntry]:
    entries: list[SessionEntry] = []
    for line in lines:
        if not line.strip():
            continue

        entries.append(entry_from_json_line(line))

    return entries
