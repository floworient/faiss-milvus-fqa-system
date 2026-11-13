import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Sequence, TextIO

from app.evaluation.runner import EvaluationRunner, load_jsonl


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: EvaluationRunner | None = None,
    stdout: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Evaluate retrieval against JSONL labels")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument(
        "--mode", choices=("vector", "keyword", "hybrid"), default="hybrid"
    )
    parser.add_argument("--top-k", type=int, default=5)
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.top_k <= 50:
        parser.error("--top-k must be between 1 and 50")
    if runner is None:
        from app.core.config import Settings
        from app.main import build_service_container

        services = build_service_container(Settings())
        runner = services.evaluation
    if runner is None:
        raise RuntimeError("evaluation service is not configured")
    with arguments.dataset.open("r", encoding="utf-8") as stream:
        report = runner.run(load_jsonl(stream), arguments.mode, arguments.top_k)
    output = stdout or sys.stdout
    output.write(json.dumps(asdict(report), ensure_ascii=False, indent=2) + "\n")
    return 0


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
