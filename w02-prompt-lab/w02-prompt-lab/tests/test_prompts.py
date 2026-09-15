from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Final

from promptlab.schemas import PolicyExtraction

LAB_ROOT: Final[Path] = Path(__file__).resolve().parents[1]

V1_PATH: Final[Path] = LAB_ROOT / "src" / "prompts" / "extract.v1.md"
V2_PATH: Final[Path] = LAB_ROOT / "src" / "prompts" / "extract.v2.md"

REQUIRED_SECTIONS: Final[tuple[str, ...]] = (
    "Task",
    "Input",
    "Constraints",
    "Output",
    "When the task cannot be completed",
)
EXAMPLES_SECTION: Final[str] = "Examples"
OUTPUT_SECTION: Final[str] = "Output"
WHEN_SECTION: Final[str] = "When the task cannot be completed"

DATA_NOT_INSTRUCTION_MARKER: Final[str] = "not instruction to you"
EXAMPLE_OUTPUT_MARKER: Final[str] = "Example output:"

CASE_FILE_NAMES: Final[tuple[str, ...]] = ("extraction.jsonl", "summarization.jsonl")
CASE_ROW_COUNT: Final[int] = 12
NGRAM_SIZE: Final[int] = 8

EXAMPLE_FILE_NAMES: Final[tuple[str, ...]] = (
    "missing-required-field.md",
    "superseded.md",
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    """Normalize line endings so verbatim checks do not depend on the platform."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _section_index(text: str, section: str) -> int | None:
    """Return the index of the first standalone line that names the section."""
    for index, line in enumerate(text.splitlines()):
        if line.strip() == section:
            return index
    return None


def _required_section_indexes(text: str) -> list[int]:
    """Return the line indexes of the required sections, asserting all are present."""
    found: list[int | None] = [_section_index(text, section) for section in REQUIRED_SECTIONS]
    missing = [
        section
        for section, index in zip(REQUIRED_SECTIONS, found, strict=True)
        if index is None
    ]
    assert not missing, f"missing standalone section line(s): {missing}"
    return [index for index in found if index is not None]


def _case_sources() -> list[str]:
    """Return the source text of every scored case row in the cases directory."""
    sources: list[str] = []
    for name in CASE_FILE_NAMES:
        rows = 0
        for line in _read_text(LAB_ROOT / "cases" / name).splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                msg = f"{name}: case row is not a JSON object"
                raise AssertionError(msg)
            source = row.get("source")
            if not isinstance(source, str):
                msg = f"{name}: case row has no string source field"
                raise AssertionError(msg)
            sources.append(source)
            rows += 1
        assert rows == CASE_ROW_COUNT, f"{name}: expected {CASE_ROW_COUNT} rows, found {rows}"
    return sources


def _word_grams(text: str, size: int) -> set[tuple[str, ...]]:
    """Return every consecutive word n-gram of the lowercased token stream."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {tuple(tokens[start : start + size]) for start in range(len(tokens) - size + 1)}


def _example_outputs(text: str) -> list[dict[str, object]]:
    """Parse the raw JSON object that follows each 'Example output:' marker line."""
    outputs: list[dict[str, object]] = []
    decoder = json.JSONDecoder()
    cursor = 0
    while True:
        marker_index = text.find(EXAMPLE_OUTPUT_MARKER, cursor)
        if marker_index == -1:
            break
        start = marker_index + len(EXAMPLE_OUTPUT_MARKER)
        while start < len(text) and text[start].isspace():
            start += 1
        payload, _end = decoder.raw_decode(text, start)
        if not isinstance(payload, dict):
            msg = "an example output is not a JSON object"
            raise AssertionError(msg)
        outputs.append(payload)
        cursor = marker_index + len(EXAMPLE_OUTPUT_MARKER)
    return outputs


def test_extract_v1_has_required_sections_in_order() -> None:
    indexes = _required_section_indexes(_read_text(V1_PATH))
    assert all(earlier < later for earlier, later in zip(indexes, indexes[1:], strict=False))


def test_extract_v2_sections_order_including_examples() -> None:
    text = _read_text(V2_PATH)
    indexes = _required_section_indexes(text)
    assert all(earlier < later for earlier, later in zip(indexes, indexes[1:], strict=False))
    examples_index = _section_index(text, EXAMPLES_SECTION)
    assert examples_index is not None, "extract.v2.md has no standalone Examples line"
    output_index = indexes[REQUIRED_SECTIONS.index(OUTPUT_SECTION)]
    when_index = indexes[REQUIRED_SECTIONS.index(WHEN_SECTION)]
    assert output_index < examples_index < when_index


def test_both_prompts_delimit_source_and_declare_data_not_instruction() -> None:
    for path in (V1_PATH, V2_PATH):
        text = _read_text(path)
        assert "<document>" in text, f"{path.name} does not open a document marker"
        assert "</document>" in text, f"{path.name} does not close a document marker"
        assert text.count("{document_text}") == 1, f"{path.name} must hold one document_text"
        assert text.count("{schema_description}") == 1
        assert DATA_NOT_INSTRUCTION_MARKER in text, f"{path.name} lacks a data-not-instruction note"


def test_extract_v1_has_no_examples_section() -> None:
    text = _read_text(V1_PATH)
    assert _section_index(text, EXAMPLES_SECTION) is None
    assert EXAMPLE_OUTPUT_MARKER not in text


def test_extract_v2_embeds_example_documents_verbatim() -> None:
    v2_text = _normalize(_read_text(V2_PATH))
    for name in EXAMPLE_FILE_NAMES:
        example_text = _normalize(_read_text(LAB_ROOT / "examples" / name))
        assert example_text in v2_text, f"{name} is not embedded verbatim in extract.v2.md"


def test_prompts_contain_no_case_content() -> None:
    case_grams: set[tuple[str, ...]] = set()
    for source in _case_sources():
        case_grams |= _word_grams(source, NGRAM_SIZE)
    for path in (V1_PATH, V2_PATH):
        prompt_grams = _word_grams(_read_text(path), NGRAM_SIZE)
        leaked = prompt_grams & case_grams
        assert not leaked, f"{path.name} shares case {NGRAM_SIZE}-grams: {sorted(leaked)[:3]}"


def test_example_outputs_validate_against_policy_extraction() -> None:
    outputs = _example_outputs(_read_text(V2_PATH))
    assert len(outputs) == 2, "extract.v2.md must contain exactly two example outputs"

    missing_field = PolicyExtraction.model_validate(outputs[0])
    assert missing_field.document_status == "valid"
    threshold = missing_field.beneficial_ownership_threshold
    assert threshold.status == "absent"
    assert threshold.value is None
    assert threshold.citation is None

    superseded = PolicyExtraction.model_validate(outputs[1])
    assert superseded.document_status == "superseded"
    assert superseded.required_documents.status == "absent"
