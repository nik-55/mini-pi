from agent.session.entries import SessionEntry


class SessionTreeError(ValueError):
    pass


def entries_by_id(entries: list[SessionEntry]) -> dict[str, SessionEntry]:
    result: dict[str, SessionEntry] = {}
    for entry in entries:
        if entry.id in result:
            raise SessionTreeError(f"Duplicate entry '{entry.id}' found")
        result[entry.id] = entry

    return result


def branch_by_leaf_id(entries: list[SessionEntry], leaf_id: str) -> list[SessionEntry]:
    entries_mapping = entries_by_id(entries)

    active_branch: list[SessionEntry] = []

    seen: set[str] = set()
    current_id: str | None = leaf_id

    while current_id is not None:
        if current_id in seen:
            raise SessionTreeError()

        entry = entries_mapping.get(current_id)
        if entry is None:
            raise SessionTreeError(f"Missing session entry: {current_id}")

        seen.add(current_id)
        active_branch.append(entry)
        current_id = entry.parent_id

    active_branch.reverse()
    return active_branch
