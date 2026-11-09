"""Recorded annual-report pages and model answers, shared by the annual-report tests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from finn.llm.client import Llm, MemoryStore

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
REPORTS = FIXTURES / "nse" / "annual_reports"


def report(name: str) -> dict[str, Any]:
    return json.loads((REPORTS / f"{name}.json").read_text())


def full_pages(name: str) -> tuple[list[str], list[tuple[int, str, int]]]:
    """The report as a page list: recorded pages in place, the rest blank."""
    d = report(name)
    pages = [""] * int(d["total_pages"])
    for n, text in d["pages"].items():
        pages[int(n) - 1] = text
    return pages, [(int(a), str(b), int(c)) for a, b, c in d["outline"]]


def page_map(name: str) -> dict[int, str]:
    return {int(n): t for n, t in report(name)["pages"].items()}


def recorded(task: str) -> Any:
    return json.loads((FIXTURES / "llm" / f"annual_INFY_FY26_{task}.json").read_text())


# Words that pick out each prompt's system instruction.
_TASKS = {
    "statement of profit and loss and the statement of cash flows": "statements",
    "independent auditor's report": "auditor",
    "Business Responsibility and Sustainability": "business",
    "Management Discussion and Analysis": "risks",
    "bull case and the bear case": "case",
}


class Recorded:
    """A model transport that answers each task with its recorded answer."""

    def __init__(self, overrides: Mapping[str, Any] | None = None):
        self.overrides = dict(overrides or {})
        self.tasks: list[str] = []

    def __call__(
        self, url: str, body: Mapping[str, Any], headers: Mapping[str, str], timeout: float
    ) -> Any:
        text = json.dumps(body)
        task = next(t for words, t in _TASKS.items() if words in text)
        self.tasks.append(task)
        answer = self.overrides.get(task, recorded(task))
        return {
            "candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}}],
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50},
        }


def recorded_llm(overrides: Mapping[str, Any] | None = None) -> tuple[Llm, Recorded]:
    t = Recorded(overrides)
    return Llm("g", None, store=MemoryStore(), transport=t, retries=0), t
