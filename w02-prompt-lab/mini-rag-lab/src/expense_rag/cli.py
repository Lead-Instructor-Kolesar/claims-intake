from __future__ import annotations

import argparse
import json
import sys

from expense_rag.config import load_settings
from expense_rag.eval_cases import REQUIRED_QUESTIONS, evaluate
from expense_rag.generate import answer_question
from expense_rag.ingest import ingest_policy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Grounded employee expense-policy assistant"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ingest", help="Chunk, embed, and store policy.md")

    ask = sub.add_parser("ask", help="Ask a question against the stored policy")
    ask.add_argument("question", nargs="+", help="User question")

    sub.add_parser("eval", help="Run the six required test questions")

    args = parser.parse_args(argv)
    settings = load_settings()

    if args.command == "ingest":
        chunks = ingest_policy(settings)
        print(f"Stored {len(chunks)} policy chunks:")
        for chunk in chunks:
            print(f"  {chunk.chunk_id}  {chunk.section_label}")
        return 0

    if args.command == "ask":
        question = " ".join(args.question)
        result = answer_question(settings, question)
        json.dump(result.to_response(), sys.stdout, indent=2)
        print()
        return 0

    if args.command == "eval":
        report = evaluate(settings, REQUIRED_QUESTIONS)
        json.dump(report, sys.stdout, indent=2)
        print()
        failures = [item for item in report["results"] if not item["ok"]]
        return 1 if failures else 0

    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
