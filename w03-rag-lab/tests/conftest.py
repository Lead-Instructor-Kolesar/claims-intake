from __future__ import annotations

from datetime import date

import pytest

from rag.corpus import DocumentMeta

FIXTURE_BODY = """4.1 Purpose

This policy sets out the periodic review requirements for small business
customers.

4.2 Required documentation

For partnerships, the reviewer shall obtain the partnership agreement, proof of
registered address, and identification for each partner holding 25 percent or
more of the partnership interest. Where the partnership is registered outside
the jurisdictions listed in Appendix A, the reviewer shall instead apply
Section 6.4.
"""


@pytest.fixture
def fixture_meta() -> DocumentMeta:
    return DocumentMeta(
        doc_id="kyc-ie-0004",
        title="Small Business Periodic KYC Review Policy (Ireland)",
        family="kyc_periodic_review",
        version="v4.2",
        effective_date=date(2025, 11, 1),
        superseded_by=None,
        jurisdiction="IE",
        entity_types=["partnership", "private_limited_company"],
        source_path="corpus/source/kyc-ie-0004-v4.2.md",
        source_sha256="0" * 64,
    )


@pytest.fixture
def fixture_body() -> str:
    return FIXTURE_BODY
