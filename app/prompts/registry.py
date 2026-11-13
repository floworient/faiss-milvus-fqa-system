from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Mapping

from app.core.errors import AppError


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    name: str
    version: str
    required: frozenset[str]
    body: str


class PromptRegistry:
    def __init__(self, template_dir: Path) -> None:
        self.template_dir = Path(template_dir)
        self.templates: dict[tuple[str, str], PromptTemplate] = {}
        for path in sorted(self.template_dir.glob("*.txt")):
            template = self._load(path)
            key = (template.name, template.version)
            if key in self.templates:
                raise ValueError(f"duplicate prompt template: {key}")
            self.templates[key] = template

    @classmethod
    def default(cls) -> "PromptRegistry":
        return cls(Path(__file__).parent / "templates")

    def render(
        self, name: str, version: str, variables: Mapping[str, str]
    ) -> str:
        template = self.templates.get((name, version))
        if template is None:
            raise AppError(
                "prompt_template_not_found", "Prompt template was not found.", 500
            )
        missing = sorted(template.required - variables.keys())
        if missing:
            raise AppError(
                "prompt_variables_missing",
                "Prompt variables are incomplete.",
                500,
                {"missing": missing},
            )
        return template.body.format_map(dict(variables))

    @staticmethod
    def _load(path: Path) -> PromptTemplate:
        raw = path.read_text("utf-8")
        if not raw.startswith("---\n") or "\n---\n" not in raw[4:]:
            raise ValueError(f"invalid prompt metadata: {path}")
        header, body = raw[4:].split("\n---\n", 1)
        metadata: dict[str, str] = {}
        for line in header.splitlines():
            key, separator, value = line.partition(":")
            if not separator:
                raise ValueError(f"invalid prompt metadata line: {line}")
            metadata[key.strip()] = value.strip()
        required = frozenset(
            item.strip() for item in metadata.get("required", "").split(",") if item.strip()
        )
        placeholders = {
            field_name
            for _, field_name, _, _ in Formatter().parse(body)
            if field_name
        }
        missing = required - placeholders
        if missing:
            raise ValueError(f"missing placeholders: {sorted(missing)}")
        try:
            return PromptTemplate(
                metadata["name"], metadata["version"], required, body.strip()
            )
        except KeyError as error:
            raise ValueError(f"missing prompt metadata: {error.args[0]}") from error

