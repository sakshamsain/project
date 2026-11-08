from collections.abc import Mapping
from typing import Any

import pytest

from finn.llm.client import Llm, LlmError, MemoryStore, ProviderError, shadow_cost, tier_models


def test_tiers_come_from_models_yaml() -> None:
    t2 = tier_models("t2_reader")
    assert t2[0].provider == "gemini" and len(t2) >= 2
    with pytest.raises(LlmError):
        tier_models("t9_imaginary")


def test_shadow_cost_uses_list_prices_only_when_known() -> None:
    assert shadow_cost("gemini-3.1-flash-lite", 1_000_000, 0) == pytest.approx(0.25)
    assert shadow_cost("gemini-3.6-flash", 1_000_000, 1_000_000) == 0.0  # price not verified


def _gemini_ok(text: str) -> dict[str, Any]:
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }


class Fake:
    def __init__(self, answers: list[Any]):
        self.answers = answers
        self.urls: list[str] = []

    def __call__(
        self, url: str, body: Mapping[str, Any], headers: Mapping[str, str], timeout: float
    ) -> Any:
        self.urls.append(url)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def test_falls_back_when_the_primary_fails_and_caches_the_answer() -> None:
    fake = Fake([ProviderError(400, "bad"), _gemini_ok('{"n": 3}')])
    store = MemoryStore()
    llm = Llm("g", "q", store=store, transport=fake, retries=0)
    r = llm.json("t", "t2_reader", "v1", "sys", "user", {"type": "object"})
    assert r.data == {"n": 3} and not r.cache_hit
    assert [c["ok"] for c in store.calls] == [False, True]
    again = llm.json("t", "t2_reader", "v1", "sys", "user", {"type": "object"})
    assert again.cache_hit and again.data == {"n": 3}


def test_an_answer_that_fails_validation_moves_to_the_next_model() -> None:
    fake = Fake([_gemini_ok('{"n": -1}'), _gemini_ok('{"n": 2}')])
    llm = Llm("g", "q", store=MemoryStore(), transport=fake, retries=0)

    def positive(d: Any) -> None:
        if d["n"] < 0:
            raise ValueError("negative")

    r = llm.json("t", "t2_reader", "v1", "s", "u", {"type": "object"}, validate=positive)
    assert r.data == {"n": 2} and len(fake.urls) == 2


def test_every_model_failing_raises() -> None:
    fake = Fake([ProviderError(400, "x")] * 5)
    llm = Llm("g", None, store=MemoryStore(), transport=fake, retries=0)
    with pytest.raises(LlmError):
        llm.json("t", "t2_reader", "v1", "s", "u", {"type": "object"})
