"""Unit tests for flex prompt budget allocation."""
from __future__ import annotations

import uuid

import pytest

from app.config.settings import invalidate_settings_cache
from app.domain.services.budget_mode import BudgetMode
from app.domain.services.context_budget_manager import ContextBudgetManager
from app.domain.services.context_builder import ContextBuilder
from app.infrastructure.database.models.emotion_state import EmotionState
from app.shared.utils.token_estimator import TokenEstimator


@pytest.fixture(autouse=True)
def _refresh_settings():
    invalidate_settings_cache()
    yield
    invalidate_settings_cache()


def _make_long(word: str, chars: int) -> str:
    repeats = max(1, chars // max(len(word), 1))
    return (word * repeats)[:chars]


def test_token_estimator_trim():
    text = "a" * 1000
    trimmed = TokenEstimator.trim_to_budget(text, 100, suffix="...")
    assert TokenEstimator.estimate(trimmed) <= 100


def test_empty_lore_reallocates_to_history():
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": _make_long(f"m{i}", 400)}
        for i in range(12)
    ]
    without_lore = ContextBudgetManager.allocate(
        mode=BudgetMode.RAG,
        system_fixed_tokens=1815,
        user_message="hello senpai",
        lore_chunks=[_make_long("L", 600)],
        memories=[],
        history=history,
        tool_result="",
    )
    with_realloc = ContextBudgetManager.allocate(
        mode=BudgetMode.RAG,
        system_fixed_tokens=1815,
        user_message="hello senpai",
        lore_chunks=[],
        memories=[],
        history=history,
        tool_result="",
    )
    assert "lore" in with_realloc.audit.reallocated_from
    assert with_realloc.audit.grants["history"] >= without_lore.audit.grants["history"]


def test_factual_other_prioritizes_search_over_lore():
    lore = [_make_long("Lore", 2000)]
    search = _make_long("SearchResult ", 10000)
    allocation = ContextBudgetManager.allocate(
        mode=BudgetMode.LOOP,
        system_fixed_tokens=1815,
        user_message="Thien An Mon 1989?",
        lore_chunks=lore,
        memories=[],
        history=[],
        conversation_summary=None,
        tool_result=search,
        intent_name="OTHER",
    )
    assert allocation.audit.priority_profile == "factual_other"
    assert allocation.audit.grants["search"] >= allocation.audit.grants["lore"]


def test_rag_mode_within_flex_ceiling():
    lore = [_make_long("L", 500) for _ in range(5)]
    memories = [_make_long("M", 400) for _ in range(5)]
    history = [
        {"role": "user" if i % 2 else "assistant", "content": _make_long(f"H{i}", 300)}
        for i in range(20)
    ]
    allocation = ContextBudgetManager.allocate(
        mode=BudgetMode.RAG,
        system_fixed_tokens=1815,
        user_message="test question",
        lore_chunks=lore,
        memories=memories,
        history=history,
    )
    assert allocation.audit.total_used <= allocation.audit.effective_ceiling


def test_context_builder_returns_audit():
    emotion = EmotionState(
        user_id=uuid.uuid4(),
        joy=0.5,
        sadness=0.1,
        trust=0.5,
        irritation=0.1,
        attachment=0.5,
        updated_at=0,
    )
    builder = ContextBuilder()
    result = builder.build(
        emotion=emotion,
        attachment_bonus=0.05,
        memories=[],
        lore=[],
        history=[{"role": "user", "content": "chào em"}],
        user_message="chào em",
        intent_name="OTHER",
        budget_mode=BudgetMode.SMALL_TALK,
    )
    assert result.prompt.system
    assert result.audit.mode == "small_talk"
    assert result.audit.within_budget


def test_summary_trimmed_when_too_long():
    long_summary = _make_long("Summary", 8000)
    allocation = ContextBudgetManager.allocate(
        mode=BudgetMode.RAG,
        system_fixed_tokens=1815,
        user_message="hi",
        lore_chunks=[],
        memories=[],
        history=[],
        conversation_summary=long_summary,
    )
    assert allocation.trimmed_summary is not None
    assert "summary" in allocation.audit.trimmed_sections
    assert TokenEstimator.estimate(allocation.trimmed_summary or "") < TokenEstimator.estimate(long_summary)


def test_hybrid_anchor_window_when_summary_exists():
    # 20 short messages (10 turns)
    short_history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
        for i in range(20)
    ]
    summary_text = "Tóm tắt từ câu 0 đến câu 18..."

    # Case 1: At interaction 11 (1 turn since turn-10 summary)
    # Expected messages kept: max(4, (1 + 2) * 2) = 6 messages (recent 3 turns: msgs 14, 15, 16, 17, 18, 19)
    alloc_turn_11 = ContextBudgetManager.allocate(
        mode=BudgetMode.RAG,
        system_fixed_tokens=1815,
        user_message="câu 11 nè em",
        lore_chunks=[],
        memories=[],
        history=short_history,
        conversation_summary=summary_text,
        interaction_count=11,
    )
    assert len(alloc_turn_11.trimmed_history) == 6
    assert alloc_turn_11.trimmed_history[-1]["content"] == "msg 19"
    assert alloc_turn_11.trimmed_history[0]["content"] == "msg 14"

    # Case 2: At interaction 10 (just generated summary for turns 1-10)
    # Expected messages kept: max(4, (0 + 2) * 2) = 4 messages (2 safety overlap turns: msgs 16, 17, 18, 19)
    alloc_turn_10 = ContextBudgetManager.allocate(
        mode=BudgetMode.RAG,
        system_fixed_tokens=1815,
        user_message="câu 10",
        lore_chunks=[],
        memories=[],
        history=short_history,
        conversation_summary=summary_text,
        interaction_count=10,
    )
    assert len(alloc_turn_10.trimmed_history) == 4
    assert alloc_turn_10.trimmed_history[-1]["content"] == "msg 19"
    assert alloc_turn_10.trimmed_history[0]["content"] == "msg 16"

    # Case 3: Without summary (early in conversation, e.g. interaction 5)
    # Without summary, no anchor window limit is enforced -> all short messages fitting within budget are kept
    alloc_no_summary = ContextBudgetManager.allocate(
        mode=BudgetMode.RAG,
        system_fixed_tokens=1815,
        user_message="câu hỏi đầu",
        lore_chunks=[],
        memories=[],
        history=short_history,
        conversation_summary=None,
        interaction_count=5,
    )
    assert len(alloc_no_summary.trimmed_history) == 20




