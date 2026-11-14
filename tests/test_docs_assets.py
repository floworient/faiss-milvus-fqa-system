from pathlib import Path
from xml.etree import ElementTree

import pytest


ASSETS = [
    Path("docs/image/rag-qa-logo.svg"),
    Path("docs/image/rag-qa-architecture.svg"),
]


@pytest.mark.parametrize("asset", ASSETS)
def test_svg_asset_is_accessible_and_self_contained(asset: Path) -> None:
    root = ElementTree.parse(asset).getroot()
    assert root.tag.endswith("svg")
    assert root.get("viewBox")
    assert any(child.tag.endswith("title") and (child.text or "").strip() for child in root)

    serialized = asset.read_text("utf-8").lower()
    assert "<script" not in serialized
    for element in root.iter():
        for name, value in element.attrib.items():
            if name.endswith("href"):
                assert not value.startswith(("http://", "https://"))


def test_architecture_diagram_names_implemented_components() -> None:
    content = ASSETS[1].read_text("utf-8")
    for label in (
        "FastAPI",
        "Ingestion",
        "Faiss",
        "Keyword / BM25",
        "RRF",
        "Agent",
        "Memory",
        "Tiered LLM",
        "Evaluation",
    ):
        assert label in content
