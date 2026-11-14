"""Materialize an evaluation JSONL file with the uploaded document ID."""

import argparse
import json
import re
from pathlib import Path


DOCUMENT_ID_PATTERN = re.compile(r"doc_[0-9a-f]{32}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-id", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "fixtures" / "evaluation.runtime.jsonl",
    )
    arguments = parser.parse_args()
    if DOCUMENT_ID_PATTERN.fullmatch(arguments.document_id) is None:
        parser.error("--document-id must match doc_<32 lowercase hex characters>")

    template = Path(__file__).parent / "fixtures" / "evaluation.template.jsonl"
    rows = []
    for line in template.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        row["relevant_document_ids"] = [arguments.document_id]
        rows.append(json.dumps(row, ensure_ascii=False))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"Generated evaluation fixture at {arguments.output.resolve()}")


if __name__ == "__main__":
    main()
