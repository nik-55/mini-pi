from pathlib import Path
import re

from pydantic import BaseModel


class ProjectContextFile(BaseModel):
    path: Path
    content: str


class Skill(BaseModel):
    name: str
    description: str
    path: Path
    content: str


def discover_project_context(cwd: Path | None = None) -> list[ProjectContextFile]:
    work_dir = cwd or Path.cwd()

    candidates: list[Path] = (
        work_dir / "AGENTS.md",
        work_dir / ".mini-pi" / "AGENTS.md",
    )

    context_files: list[ProjectContextFile] = []

    for path in candidates:
        if not path.is_file():
            continue

        try:
            content = path.read_text(encoding="utf-8") or ""
            context_files.append(ProjectContextFile(path=path, content=content))

        except Exception as exc:
            print(
                f"[Warning] could not read context file from  {path}: {exc}", flush=True
            )

    return context_files


def format_project_context(context_files: list[ProjectContextFile]) -> str:
    if not context_files:
        return ""

    lines = [
        "\n\n<project_context>",
        "Project Specific Instructions and Guidelines:",
    ]

    for file in context_files:
        lines.append(f"<project_instructions path='{file.path}'>")
        lines.append(file.content.strip())
        lines.append(f"</project_instructions>\n")

    lines.append("</project_context>")

    return "\n".join(lines)


def _parse_skill_file(path: Path) -> Skill | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"[Warning] could not read skill at '{path}: {exc}'", flush=True)
        return

    if not raw.strip():
        return

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.DOTALL)

    if not match:
        # path.name is SKILL.md
        name = path.parent.name
        description = "No description provided"
        body = raw.strip()
    else:
        formatter, body = match.group(1), match.group(2)

        metadata: dict[str, str] = {}

        for line in formatter.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                metadata[key.strip()] = val.strip()

        name = metadata.get("name", path.parent.name)
        description = metadata.get("description", "No description provided")

    return Skill(
        name=name,
        description=description,
        path=path,
        content=body,
    )


def discover_skills(cwd: Path | None = None) -> list[Skill]:
    work_dir = cwd or Path.cwd()
    skill_dirs: list[Path] = (work_dir / ".mini-pi" / "skills",)

    skills: list[Skill] = []

    for skill_dir in skill_dirs:
        if not skill_dir.is_dir():
            continue

        for child in skill_dir.iterdir():
            candidate = None

            if child.is_dir():
                candidate = child / "SKILL.md"
            elif child.name == "SKILL.md":
                candidate = child

            if candidate is not None and candidate.is_file():
                skill = _parse_skill_file(candidate)

                if skill is not None:
                    skills.append(skill)

    return skills


def format_skills(skills: list[Skill]) -> str:
    if not skills:
        return ""

    lines = [
        "\n\nThe following skills provide specialized instructions for a specific tasks. \
            Read the full skill file using the `read` tool when task matches its description",
        "<available_skills>\n",
    ]

    for s in skills:
        lines.append(f"""<skill>
<name>{s.name}</name>
<description>{s.description}</description>
<location>{s.path}</location>
</skill>
""")

    lines.append("</available_skills>")

    return "\n".join(lines)
