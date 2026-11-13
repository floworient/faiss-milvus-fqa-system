import pytest

from app.ingestion.parsers import DocumentValidationError, ParserRegistry


@pytest.fixture
def registry() -> ParserRegistry:
    return ParserRegistry()


def test_txt_parser_decodes_utf8_and_normalizes_source_name(
    registry: ParserRegistry,
) -> None:
    documents = registry.parse("doc_1", "../客户问题.txt", "如何退货？".encode())

    assert len(documents) == 1
    assert documents[0].source_name == "客户问题.txt"
    assert documents[0].text == "如何退货？"


def test_markdown_parser_preserves_title_and_headings(registry: ParserRegistry) -> None:
    content = "# 售后知识库\n\n## 退货\n七天内可以退货。\n"

    document = registry.parse("doc_2", "guide.md", content.encode())[0]

    assert document.title == "售后知识库"
    assert document.metadata["headings"] == ["售后知识库", "退货"]
    assert "七天内可以退货" in document.text


def test_json_parser_supports_faq_array(registry: ParserRegistry) -> None:
    documents = registry.parse(
        "doc_3",
        "faq.json",
        '[{"question":"如何退货","answer":"七天内申请"}]'.encode(),
    )

    assert len(documents) == 1
    assert documents[0].text == "问题：如何退货\n答案：七天内申请"
    assert documents[0].metadata["json_index"] == 0


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ('{"text":"通用文本"}', "通用文本"),
        ('{"content":"正文内容"}', "正文内容"),
        ('[{"text":"第一段"},{"content":"第二段"}]', "第一段"),
    ],
)
def test_json_parser_supports_general_text_shapes(
    registry: ParserRegistry, payload: str, expected: str
) -> None:
    documents = registry.parse("doc_4", "data.json", payload.encode())

    assert documents[0].text == expected


@pytest.mark.parametrize("payload", [b"{broken", b'{"unknown":"value"}', b"[]"])
def test_json_validation_rejects_malformed_or_unknown_shapes(
    registry: ParserRegistry, payload: bytes
) -> None:
    with pytest.raises(DocumentValidationError) as caught:
        registry.validate("data.json", payload)

    assert caught.value.code == "invalid_json_document"


@pytest.mark.parametrize(
    ("filename", "content", "code"),
    [
        ("file.pdf", b"content", "unsupported_document_type"),
        ("empty.txt", b"  \n", "empty_document"),
        ("invalid.txt", b"\xff", "invalid_text_encoding"),
    ],
)
def test_validation_rejects_unsupported_empty_or_non_utf8_documents(
    registry: ParserRegistry, filename: str, content: bytes, code: str
) -> None:
    with pytest.raises(DocumentValidationError) as caught:
        registry.validate(filename, content)

    assert caught.value.code == code
