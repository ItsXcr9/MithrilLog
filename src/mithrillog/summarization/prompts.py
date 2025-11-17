from __future__ import annotations

from pathlib import Path

from ..llm import PromptTemplate

PROMPT_SYSTEM_MARKER = "--system--"
PROMPT_USER_MARKER = "--user--"


def load_prompt_template(path: Path) -> PromptTemplate:
    text = path.read_text(encoding="utf-8")
    if PROMPT_SYSTEM_MARKER not in text or PROMPT_USER_MARKER not in text:
        raise ValueError(f"Invalid prompt template format: {path}")
    system_part, user_part = text.split(PROMPT_USER_MARKER, maxsplit=1)
    system_text = system_part.replace(PROMPT_SYSTEM_MARKER, "", 1).strip()
    user_text = user_part.strip()
    return PromptTemplate(name=path.stem, system=system_text, user=user_text)

