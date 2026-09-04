"""Evidence extraction prompt for turning a source into structured evidence."""

from app.schemas.llm import LLMMessage
from app.schemas.source_result import SourceResult

EVIDENCE_SYSTEM_PROMPT = (
    "You are the Evidence Agent for an R&D intelligence workflow. Read the "
    "given source and extract only what the source text actually states. "
    "Never invent facts, benchmarks, or results that are not present in the "
    "source. Respond with a single JSON object with exactly these keys: "
    "problem, method, benchmark, result, limitation (each a string or null), "
    "technology_tags (a list of short strings), evidence_snippets (a list of "
    "short verbatim quotes from the source that support your extraction), "
    "relevance_score (a number from 0 to 1), and extraction_confidence (a "
    "number from 0 to 1). Respond with JSON only, no other text."
)


def build_evidence_messages(source: SourceResult) -> list[LLMMessage]:
    """Build the chat messages that ask an LLM to extract evidence from a source."""

    source_text = source.content or source.raw_summary or ""
    user_prompt = (
        f"Source title: {source.title}\n"
        f"Source type: {source.source_type}\n"
        f"Source url: {source.url}\n"
        f"Source text:\n{source_text}"
    )
    return [
        LLMMessage(role="system", content=EVIDENCE_SYSTEM_PROMPT),
        LLMMessage(role="user", content=user_prompt),
    ]
