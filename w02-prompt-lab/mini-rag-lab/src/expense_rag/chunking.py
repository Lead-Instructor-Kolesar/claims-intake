from __future__ import annotations

import re

from expense_rag.models import PolicyChunk

TITLE_RE = re.compile(r"^#\s+(.+?)\s*$")
SECTION_RE = re.compile(r"^##\s+(\d+)\.\s+(.+?)\s*$")
VERSION_RE = re.compile(r"Version\s+([0-9.]+)", re.IGNORECASE)


def chunk_policy(markdown: str) -> list[PolicyChunk]:
    """Split a policy document into one chunk per numbered section heading."""
    lines = markdown.splitlines()
    document = "Employee Expense Policy"
    version = "2.0"
    chunks: list[PolicyChunk] = []
    current_section: tuple[str, str] | None = None
    body: list[str] = []

    def flush() -> None:
        if current_section is None:
            return
        section, section_title = current_section
        text = "\n".join(body).strip()
        if not text:
            raise ValueError(f"Section {section} has no body text")
        chunks.append(
            PolicyChunk(
                chunk_id=f"expense-policy:v{version}:section-{section}",
                document=document,
                version=version,
                section=section,
                section_title=section_title,
                text=text,
            )
        )

    for line in lines:
        title_match = TITLE_RE.match(line)
        if title_match and current_section is None and not chunks:
            heading = title_match.group(1).strip()
            version_match = VERSION_RE.search(heading)
            if version_match:
                version = version_match.group(1)
            document = VERSION_RE.sub("", heading)
            document = re.sub(r"\s*[—–-]\s*$", "", document).strip()
            continue

        section_match = SECTION_RE.match(line)
        if section_match:
            flush()
            current_section = (section_match.group(1), section_match.group(2).strip())
            body = []
            continue

        if current_section is not None:
            body.append(line)

    flush()

    if len(chunks) != 6:
        raise ValueError(f"Expected 6 structural chunks, found {len(chunks)}")
    return chunks
