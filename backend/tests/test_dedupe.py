"""Unit tests for URL normalization, hashing, and merge-time deduplication."""

from app.schemas.source_result import SourceResult, SourceType
from app.tools.dedupe import content_hash, dedupe_results, normalize_url


def test_normalize_url_drops_fragment_trailing_slash_and_tracking_params() -> None:
    raw = "HTTPS://Example.com/paper/1706.03762/?utm_source=twitter&ref=hn#abstract"

    assert normalize_url(raw) == "https://example.com/paper/1706.03762"


def test_normalize_url_is_stable_regardless_of_query_order() -> None:
    a = normalize_url("https://example.com/x?b=2&a=1")
    b = normalize_url("https://example.com/x?a=1&b=2")

    assert a == b


def test_content_hash_is_case_and_whitespace_insensitive() -> None:
    a = content_hash("Attention Is All You Need", "summary text")
    b = content_hash("attention is all you need", "  summary text  ")

    assert a == b


def test_content_hash_differs_for_different_content() -> None:
    a = content_hash("Attention Is All You Need")
    b = content_hash("Language Models are Few-Shot Learners")

    assert a != b


def _result(url: str, content: str) -> SourceResult:
    return SourceResult(
        source_type=SourceType.ARXIV,
        title=content,
        url=url,
        normalized_url=normalize_url(url),
        content_hash=content_hash(content),
    )


def test_dedupe_results_drops_repeat_normalized_url() -> None:
    first = _result("https://arxiv.org/abs/1706.03762", "Attention Is All You Need")
    duplicate = _result("https://arxiv.org/abs/1706.03762#section-2", "Attention Is All You Need")

    deduped = dedupe_results([first, duplicate])

    assert deduped == [first]


def test_dedupe_results_drops_repeat_content_hash_across_urls() -> None:
    abstract_page = _result("https://arxiv.org/abs/1706.03762", "Attention Is All You Need")
    pdf_link = _result("https://arxiv.org/pdf/1706.03762", "Attention Is All You Need")

    deduped = dedupe_results([abstract_page, pdf_link])

    assert deduped == [abstract_page]


def test_dedupe_results_keeps_distinct_entries() -> None:
    a = _result("https://arxiv.org/abs/1706.03762", "Attention Is All You Need")
    b = _result("https://github.com/huggingface/transformers", "transformers")

    assert dedupe_results([a, b]) == [a, b]
