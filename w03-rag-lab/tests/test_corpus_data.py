"""The corpus and its labels.

These pin the properties the week's assignments and the lab depend on. If the
corpus is regenerated and one of these fails, a deliverable somewhere no longer
works.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

import pytest

from promptlab.rules import select_current_version
from rag.config import CHUNK_MAX_CHARS, REPO_ROOT
from rag.parsing import parse_labeled_header

SOURCE = REPO_ROOT / "corpus" / "source"
SOURCE_B = REPO_ROOT / "corpus" / "source-b"
CASES = REPO_ROOT / "cases" / "questions"
GOLD = REPO_ROOT / "cases" / "gold"
EXAMPLES = REPO_ROOT / "examples" / "questions"

_SECTION = re.compile(r"^(\d+\.\d+) [^\n]*\n\n(.*?)(?=\n\n\d+\.\d+ |\Z)", re.S | re.M)
_CONTROL_ROW = re.compile(r"^\|\s*(?P<key>[A-Za-z ]+?)\s*\|\s*(?P<value>.*?)\s*\|$", re.M)


def _sections(path: Path) -> dict[str, str]:
    return dict(_SECTION.findall(path.read_text(encoding="utf-8")))


class _Candidate:
    def __init__(self, doc_id: str, version: str, effective: date | None,
                 superseded: str | None) -> None:
        self.doc_id = doc_id
        self.version = version
        self.effective_date = effective
        self.superseded_by = superseded


def _parse(path: Path) -> _Candidate:
    """A correct Day 1 parser, used only to verify the corpus is what it claims."""
    text = path.read_text(encoding="utf-8")
    fields, _ = parse_labeled_header(text)
    if fields:
        return _Candidate(
            str(fields["doc_id"]), str(fields["version"]),
            fields["effective_date"], fields.get("superseded_by"),  # type: ignore[arg-type]
        )
    rows = {m.group("key").lower(): m.group("value") for m in _CONTROL_ROW.finditer(text)}
    try:
        effective = date.fromisoformat(rows["effective date"])
    except ValueError:
        effective = None
    superseded = rows.get("superseded by")
    return _Candidate(
        rows["document id"], rows["version"], effective,
        None if superseded in (None, "None") else superseded,
    )


def _chunk_ids(root: Path) -> set[str]:
    ids: set[str] = set()
    for path in sorted(root.glob("*.md")):
        candidate = _parse(path)
        for section in _sections(path):
            ids.add(f"{candidate.doc_id}:{candidate.version}:{section}:0")
    return ids


# --- shape -----------------------------------------------------------------


def test_the_corpus_has_thirty_documents_in_both_exports() -> None:
    assert len(list(SOURCE.glob("*.md"))) == 30
    assert len(list(SOURCE_B.glob("*.md"))) == 30


def test_the_manifest_hashes_match_the_files() -> None:
    manifest = json.loads((REPO_ROOT / "corpus" / "manifest.json").read_text())
    assert manifest["document_count"] == 30
    for entry in manifest["documents"]:
        raw = (REPO_ROOT / entry["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"], entry["file"]


def test_both_header_conventions_are_present() -> None:
    labeled = [p for p in SOURCE.glob("*.md") if p.read_text().startswith("---")]
    control = [p for p in SOURCE.glob("*.md") if "## Document control" in p.read_text()]
    assert len(labeled) == 22
    assert len(control) == 8


def test_every_section_fits_in_one_chunk() -> None:
    for path in SOURCE.glob("*.md"):
        for section, text in _sections(path).items():
            assert len(text) <= CHUNK_MAX_CHARS, f"{path.name} {section}"


# --- planted defects -------------------------------------------------------


def test_only_the_two_planted_duplicate_bodies_exist() -> None:
    bodies: dict[str, list[str]] = {}
    for path in sorted(SOURCE.glob("*.md")):
        digest = hashlib.sha256(
            repr(sorted(_sections(path).items())).encode()
        ).hexdigest()
        bodies.setdefault(digest, []).append(path.stem)
    duplicates = sorted(sorted(v) for v in bodies.values() if len(v) > 1)
    assert duplicates == [
        ["cdp-uk-0002-v1.3", "cdp-uk-0014-v1.3"],
        ["kyc-uk-0019-v2.2", "kyc-uk-0019-v2.3"],
    ]


def test_the_duplicate_pair_disagrees_on_supersession() -> None:
    a = _parse(SOURCE / "cdp-uk-0002-v1.3.md")
    b = _parse(SOURCE / "cdp-uk-0014-v1.3.md")
    assert a.superseded_by == "v2.0"
    assert b.superseded_by is None


def test_two_documents_carry_an_unparseable_effective_date() -> None:
    undated = sorted(
        p.stem for p in SOURCE.glob("*.md") if _parse(p).effective_date is None
    )
    assert undated == ["cmp-ie-0021-v1.4", "cmp-uk-0041-v3.1"]


def test_one_document_carries_a_note_addressed_to_the_reader() -> None:
    carriers = [p.stem for p in SOURCE.glob("*.md")
                if "automated assistant" in p.read_text()]
    assert carriers == ["cdp-uk-0021-v3.0"]


def test_the_manual_quotes_the_policy_verbatim() -> None:
    policy = _sections(SOURCE / "kyc-ie-0004-v4.2.md")["4.2"].strip()
    manual = _sections(SOURCE / "cmp-ie-0021-v1.4.md")["2.7"].strip()
    assert policy == manual


# --- corpus-b --------------------------------------------------------------


def test_corpus_b_returns_a_withdrawn_revision_as_current() -> None:
    """The lab's whole exercise. The retrieval code is correct in both builds."""
    at = date(2026, 3, 15)
    good = select_current_version([_parse(p) for p in SOURCE.glob("*.md")], at)
    bad = select_current_version([_parse(p) for p in SOURCE_B.glob("*.md")], at)

    assert good["kyc-ie-0004"] == "v4.2"
    assert bad["kyc-ie-0004"] == "v3.1"
    assert good["kyc-ie-0007"] == "v1.1"
    assert bad["kyc-ie-0007"] == "v1.0"

    differences = {k for k in good.keys() | bad.keys() if good.get(k) != bad.get(k)}
    assert differences == {"kyc-ie-0004", "kyc-ie-0007"}


def test_the_withdrawn_revision_states_a_materially_different_rule() -> None:
    current = _sections(SOURCE / "kyc-ie-0004-v4.2.md")["4.2"]
    withdrawn = _sections(SOURCE / "kyc-ie-0004-v3.1.md")["4.2"]
    assert "25 percent" in current
    assert "10 percent" in withdrawn


def test_the_corpus_b_defect_is_a_parser_gap_not_a_missing_field() -> None:
    """Day 1's nulls have no day number and stay null. corpus-b's parse once the
    reader handles the format, which is why the fix belongs in the loader."""
    text = (SOURCE_B / "kyc-ie-0004-v4.2.md").read_text()
    assert "effective_date: 01 November 2025" in text
    assert "November 2025" in (SOURCE / "cmp-ie-0021-v1.4.md").read_text()


# --- questions and labels --------------------------------------------------


def test_there_are_twenty_four_cases_and_twenty_four_labels() -> None:
    assert len(list(CASES.glob("*.json"))) == 24
    assert len(list(GOLD.glob("*.json"))) == 24
    assert len(list(EXAMPLES.glob("*.json"))) == 4


def test_case_questions_carry_no_visible_answer() -> None:
    for path in CASES.glob("*.json"):
        assert "gold" not in json.loads(path.read_text())


def test_example_questions_carry_their_expected_chunks() -> None:
    for path in EXAMPLES.glob("*.json"):
        assert json.loads(path.read_text())["gold"]["gold_chunk_ids"] is not None


def test_every_gold_chunk_id_resolves_to_a_real_section() -> None:
    known = _chunk_ids(SOURCE)
    for path in list(GOLD.glob("*.json")) + list(EXAMPLES.glob("*.json")):
        payload = json.loads(path.read_text())
        gold = payload.get("gold", payload)
        for chunk_id in gold["gold_chunk_ids"]:
            assert chunk_id in known, f"{path.name} names {chunk_id}"


@pytest.mark.parametrize(
    "reason",
    ["no_candidates", "evidence_insufficient", "evidence_conflicting",
     "outside_supported_scope"],
)
def test_every_abstention_reason_is_exercised(reason: str) -> None:
    reasons = {
        json.loads(p.read_text()).get("expected_abstention_reason")
        for p in GOLD.glob("*.json")
    }
    assert reason in reasons


def test_the_triad_is_covered() -> None:
    labels = [json.loads(p.read_text()) for p in GOLD.glob("*.json")]
    answered = [g for g in labels if g["expected_behavior"] == "answer"]
    abstained = [g for g in labels if g["expected_behavior"] == "abstain"]
    assert len(answered) == 18
    assert len(abstained) == 6


def test_a_version_boundary_pair_exists() -> None:
    """The same question either side of an effective date, with different answers."""
    before = json.loads((GOLD / "q03.json").read_text())
    after = json.loads((GOLD / "q04.json").read_text())
    assert before["applicable_version"] == "v4.2"
    assert after["applicable_version"] == "v4.3"
    assert before["gold_chunk_ids"] != after["gold_chunk_ids"]
