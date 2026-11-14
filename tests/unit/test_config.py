from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app


def test_settings_create_runtime_directories(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "runtime")

    settings.ensure_directories()

    assert settings.data_dir.is_dir()
    assert settings.uploads_dir.is_dir()
    assert settings.indexes_dir.is_dir()
    assert settings.tasks_dir.is_dir()
    assert settings.sessions_dir.is_dir()


def test_dashscope_base_url_defaults_to_native_api_v1() -> None:
    settings = Settings(_env_file=None)

    assert (
        settings.dashscope_base_url
        == "https://dashscope.aliyuncs.com/api/v1"
    )


def test_dashscope_base_url_reads_environment_and_removes_trailing_slashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "RAG_DASHSCOPE_BASE_URL", "https://gateway.example.com/custom/v1///"
    )

    settings = Settings(_env_file=None)

    assert settings.dashscope_base_url == "https://gateway.example.com/custom/v1"


def test_dashscope_base_url_rejects_non_http_scheme() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, dashscope_base_url="ftp://gateway.example.com/v1")


@pytest.mark.parametrize(
    "base_url",
    [
        "https:/gateway.example.com/api/v1",
        "https://gateway.example.com/api/v1?tenant=example",
        "https://gateway.example.com/api/v1#fragment",
    ],
)
def test_dashscope_base_url_rejects_values_unsafe_for_sdk_path_join(
    base_url: str,
) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, dashscope_base_url=base_url)


@pytest.mark.parametrize("overlap", [-0.01, 0.51])
def test_settings_reject_overlap_outside_0_to_0_5(
    tmp_path: Path, overlap: float
) -> None:
    with pytest.raises(ValidationError):
        Settings(data_dir=tmp_path / "runtime", chunk_overlap_ratio=overlap)


@pytest.mark.asyncio
async def test_health_returns_status_and_request_id(tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=tmp_path / "runtime"))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    request_id = response.headers.get("x-request-id")
    assert request_id is not None
    assert request_id.startswith("req_")
