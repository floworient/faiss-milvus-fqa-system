import io
import json
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings
from app.domain.documents import Chunk
from app.domain.retrieval import RetrievalResult
from app.evaluation.cli import main as evaluation_main
from app.evaluation.runner import EvaluationRunner
from app.main import ServiceContainer, create_app
from app.retrieval.keyword import RankedChunk


def ranked(chunk_id: str, document_id: str, rank: int) -> RankedChunk:
    return RankedChunk(
        Chunk(chunk_id, document_id, chunk_id, 0, 1, {"source_name": "eval.md"}),
        rank,
        1.0 / rank,
    )


class FixedRetrieval:
    rankings = {
        "q1": [ranked("c1", "d1", 1)],
        "q2": [ranked("other", "dx", 1), ranked("c2", "d2", 2)],
        "q3": [ranked("c3", "d3", 1)],
    }

    def search(self, query: str, mode: str, top_k: int, candidate_k: int):
        return RetrievalResult(query, mode, self.rankings[query][:top_k])


def evaluation_app(tmp_path: Path):
    runner = EvaluationRunner(FixedRetrieval())
    app = create_app(
        Settings(data_dir=tmp_path / "runtime"),
        ServiceContainer(evaluation=runner),
    )
    return app, runner


async def post_evaluation(app: object, content: bytes, **data) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(
            "/api/v1/evaluations/retrieval",
            files={"file": ("evaluation.jsonl", content, "application/jsonl")},
            data=data,
        )


@pytest.mark.asyncio
async def test_evaluation_api_and_cli_return_same_reproducible_report(
    tmp_path: Path,
) -> None:
    fixture = Path("tests/fixtures/evaluation.jsonl")
    app, runner = evaluation_app(tmp_path)

    response = await post_evaluation(
        app, fixture.read_bytes(), mode="hybrid", top_k="2", dataset_name="fixture"
    )
    stdout = io.StringIO()
    exit_code = evaluation_main(
        ["--dataset", str(fixture), "--mode", "hybrid", "--top-k", "2"],
        runner=runner,
        stdout=stdout,
    )

    assert response.status_code == 200
    assert exit_code == 0
    assert response.json() == json.loads(stdout.getvalue())
    assert response.json()["query_count"] == 3
    assert response.json()["hit_at_1"] == pytest.approx(2 / 3)
    assert response.json()["query_count"] != 200
    assert response.json()["hit_at_1"] != 0.85


@pytest.mark.asyncio
async def test_evaluation_api_reports_invalid_jsonl_line_number(tmp_path: Path) -> None:
    app, _ = evaluation_app(tmp_path)

    response = await post_evaluation(
        app,
        b'{"query":"q1","relevant_chunk_ids":["c1"]}\n{broken\n',
        mode="hybrid",
        top_k="2",
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_evaluation_dataset"
    assert response.json()["details"] == {"line_number": 2}


@pytest.mark.asyncio
async def test_evaluation_api_rejects_out_of_range_top_k(tmp_path: Path) -> None:
    app, _ = evaluation_app(tmp_path)

    response = await post_evaluation(
        app,
        Path("tests/fixtures/evaluation.jsonl").read_bytes(),
        mode="hybrid",
        top_k="0",
    )

    assert response.status_code == 422
