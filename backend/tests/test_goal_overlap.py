"""Deterministic goal-relevance signal used by offline evidence extraction."""

from app.services.scoring import goal_overlap

GOAL = "Decide whether to invest in quantized on-device models for our robotics line."


def test_it_ranks_related_text_above_unrelated_text() -> None:
    related = (
        "4-bit quantization of transformer models reached 38ms median latency "
        "on an on-device robotics controller."
    )
    loosely_related = "Transformer inference on mobile hardware and model compression."
    unrelated = "A survey of medieval crop rotation practices in northern Europe."

    assert (
        goal_overlap(GOAL, related)
        > goal_overlap(GOAL, loosely_related)
        > goal_overlap(GOAL, unrelated)
    )
    assert goal_overlap(GOAL, unrelated) == 0.0


def test_it_ignores_how_long_the_source_is() -> None:
    """Containment against the goal, not Jaccard: padding must not dilute it."""

    text = "Quantized models for on-device robotics control."
    padded = text + " Unrelated filler sentence about weather patterns." * 40

    assert goal_overlap(GOAL, padded) == goal_overlap(GOAL, text)


def test_it_matches_across_common_word_endings() -> None:
    assert goal_overlap("quantized models", "quantization of a model") > 0


def test_it_is_bounded_and_deterministic() -> None:
    text = "Quantized on-device models for robotics."

    first = goal_overlap(GOAL, text)

    assert first == goal_overlap(GOAL, text)
    assert 0.0 <= first <= 1.0


def test_a_goal_of_only_stopwords_scores_zero_rather_than_dividing_by_zero() -> None:
    assert goal_overlap("we should decide", "anything at all") == 0.0
    assert goal_overlap("", "anything at all") == 0.0
