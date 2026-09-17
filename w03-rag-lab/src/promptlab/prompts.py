"""Prompt registry. Week 2 reference implementation.

Prompt files live in src/promptlab/prompts/ and src/rag/prompts/. Neither
directory carries an __init__.py, because this module and that directory share a
name and Python resolves it in favor of the module only while the directory is
not a package. A well-meaning tidy-up that adds one breaks every import.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from promptlab.errors import MissingPromptVariableError

MARKER_OPEN = "<document>"
MARKER_CLOSE = "</document>"

_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
_FRONT_MATTER = re.compile(r"\A---\nsystem: \|\n(?P<system>.*?)\n---\n", re.DOTALL)


class PromptTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_id: str
    version: str
    system: str
    user_template: str
    template_hash: str


def _placeholders(template: str) -> set[str]:
    return set(_PLACEHOLDER.findall(template))


def load(prompt_id: str, version: str, prompt_dir: Path) -> PromptTemplate:
    """Resolve an identifier and version to immutable text plus its hash.

    A prompt that produced a recorded result is never edited in place. A change
    is a new version file, so that a result can always be traced to the exact
    text that produced it.
    """
    path = prompt_dir / f"{prompt_id}.{version}.md"
    raw = path.read_text(encoding="utf-8")

    match = _FRONT_MATTER.match(raw)
    if match is None:
        raise ValueError(f"{path} has no system front matter block")
    system = "\n".join(
        line[2:] if line.startswith("  ") else line
        for line in match.group("system").splitlines()
    ).strip()
    user_template = raw[match.end():]

    return PromptTemplate(
        prompt_id=prompt_id,
        version=version,
        system=system,
        user_template=user_template,
        template_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )


def render_user(
    template: PromptTemplate,
    variables: Mapping[str, str],
    untrusted: str,
) -> str:
    """Render the user message, escaping the closing marker in supplied content.

    Supplied content is data. A document that carries the closing marker would
    otherwise end the delimited block early and have whatever follows read as
    instruction.
    """
    missing = _placeholders(template.user_template) - set(variables) - {"document_text"}
    if missing:
        raise MissingPromptVariableError(sorted(missing))
    sanitized = untrusted.replace(MARKER_CLOSE, "&lt;/document&gt;")
    return template.user_template.format(**variables, document_text=sanitized)
