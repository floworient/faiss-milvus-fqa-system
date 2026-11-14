from pathlib import Path

from pydantic import Field, HttpUrl, TypeAdapter, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)


class Settings(BaseSettings):
    """Runtime configuration for the single-process backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RAG_",
        extra="ignore",
    )

    data_dir: Path = Path("data/runtime")
    upload_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    chunk_min_tokens: int = Field(default=256, gt=0)
    chunk_max_tokens: int = Field(default=768, gt=0)
    chunk_overlap_ratio: float = Field(default=0.15, ge=0.0, le=0.5)
    retrieval_top_k: int = Field(default=5, gt=0)
    retrieval_candidate_k: int = Field(default=20, gt=0)
    dashscope_api_key: str | None = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    embedding_model: str = "text-embedding-v3"
    embedding_dimension: int = Field(default=512, gt=0)
    primary_llm_model: str = "qwen-plus"
    backup_llm_model: str = "qwen-turbo"
    llm_timeout_seconds: float = Field(default=30.0, gt=0)

    @field_validator("dashscope_base_url", mode="before")
    @classmethod
    def validate_dashscope_base_url(cls, value: object) -> str:
        normalized = str(value).rstrip("/")
        _HTTP_URL_ADAPTER.validate_python(normalized)
        return normalized

    @model_validator(mode="after")
    def validate_ranges(self) -> "Settings":
        if self.chunk_min_tokens > self.chunk_max_tokens:
            raise ValueError("chunk_min_tokens must not exceed chunk_max_tokens")
        if self.retrieval_top_k > self.retrieval_candidate_k:
            raise ValueError("retrieval_top_k must not exceed retrieval_candidate_k")
        return self

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def indexes_dir(self) -> Path:
        return self.data_dir / "indexes"

    @property
    def tasks_dir(self) -> Path:
        return self.data_dir / "tasks"

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    def ensure_directories(self) -> None:
        for directory in (
            self.data_dir,
            self.uploads_dir,
            self.indexes_dir,
            self.tasks_dir,
            self.sessions_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

