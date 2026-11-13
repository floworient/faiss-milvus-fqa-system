from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

