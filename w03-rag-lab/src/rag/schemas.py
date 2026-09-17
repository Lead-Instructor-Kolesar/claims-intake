"""Week 3 model-facing schemas. Day 2 work.

QueryProposal is what the rewrite prompt returns through complete_structured. A
proposed query may rephrase the analyst's question and may not introduce a fact
the question did not contain, so no jurisdiction, entity type, date, or threshold
appears in a query string. Those live on the FilterSpec, where they are
structured, checkable, and returned with the result.
"""

from __future__ import annotations
