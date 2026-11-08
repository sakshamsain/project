"""One door to the models: tiers from models.yaml, JSON out, cached and logged.

Code asks for a tier (`t2_reader`), never a model id. A call tries the tier's primary
model, then its fallbacks; the answer must parse as JSON and pass the caller's validator,
or the next model is tried. Answers are cached by (task, prompt version, model, input
hash), and every call, cache hits included, is logged with its shadow cost at the paid
list price. Prompts are closed-book and carry public filings only (CLAUDE.md rules 3, 4).
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import yaml

MODELS_FILE = Path(__file__).with_name("models.yaml")
UA = "finn-worker/0.1 (+https://github.com/sakshamsain/project)"
RETRYABLE = {429, 500, 502, 503, 504}


class LlmError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ModelSpec:
    provider: str
    model: str
    reasoning: str | None = None


@lru_cache(maxsize=1)
def _config() -> dict[str, Any]:
    data = yaml.safe_load(MODELS_FILE.read_text())
    if not isinstance(data, dict):
        raise LlmError("models.yaml is not a mapping")
    return data


def tier_models(tier: str) -> list[ModelSpec]:
    """Primary first, then fallbacks. `escalate` is used only when asked for."""
    t = _config()["tiers"].get(tier)
    if t is None:
        raise LlmError(f"unknown tier {tier!r}")
    specs = [ModelSpec(**t["primary"])]
    specs += [ModelSpec(**f) for f in t.get("fallback", [])]
    return specs


def escalation(tier: str) -> ModelSpec | None:
    t = _config()["tiers"].get(tier, {})
    return ModelSpec(**t["escalate"]) if t.get("escalate") else None


def shadow_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    price = (_config().get("paid_list_prices") or {}).get(model) or {}
    if price.get("input") is None or price.get("output") is None:
        return 0.0
    cost = (tokens_in * float(price["input"]) + tokens_out * float(price["output"])) / 1_000_000
    return round(cost, 6)


@dataclass(frozen=True, slots=True)
class LlmResult:
    data: Any
    model: str
    provider: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    cache_hit: bool


class Store(Protocol):
    def get(self, key: str) -> Any | None: ...
    def put(self, key: str, output: Any) -> None: ...
    def log(self, row: Mapping[str, Any]) -> None: ...


@dataclass
class MemoryStore:
    """For tests and dry runs."""

    cache: dict[str, Any] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def get(self, key: str) -> Any | None:
        return self.cache.get(key)

    def put(self, key: str, output: Any) -> None:
        self.cache[key] = output

    def log(self, row: Mapping[str, Any]) -> None:
        self.calls.append(dict(row))


Transport = Callable[[str, Mapping[str, Any], Mapping[str, str], float], Any]


def http_post(url: str, body: Mapping[str, Any], headers: Mapping[str, str], timeout: float) -> Any:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA, **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise ProviderError(exc.code, detail) from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ProviderError(0, str(exc)) from None


class ProviderError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status


class Llm:
    def __init__(
        self,
        gemini_key: str | None,
        groq_key: str | None,
        store: Store | None = None,
        transport: Transport = http_post,
        timeout_s: float = 180.0,
        retries: int = 2,
    ):
        self._keys = {"gemini": gemini_key, "groq": groq_key}
        self._store = store or MemoryStore()
        self._post = transport
        self._timeout = timeout_s
        self._retries = retries

    def json(
        self,
        task: str,
        tier: str,
        prompt_version: str,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int = 8192,
        validate: Callable[[Any], None] | None = None,
        escalate: bool = False,
    ) -> LlmResult:
        """The first model in the tier whose answer parses and validates."""
        input_hash = hashlib.sha256(f"{system}\x00{user}".encode()).hexdigest()
        specs = tier_models(tier)
        if escalate and (e := escalation(tier)):
            specs = [e, *specs]

        def cache_key(spec: ModelSpec) -> str:
            return hashlib.sha256(
                f"{task}|{prompt_version}|{spec.model}|{input_hash}".encode()
            ).hexdigest()

        for spec in specs:  # any model's earlier answer to the same input will do
            cached = self._store.get(cache_key(spec))
            if cached is not None:
                self._log(task, tier, spec, prompt_version, input_hash, 0, 0, 0, True, True, None)
                return LlmResult(cached, spec.model, spec.provider, 0, 0, 0, True)
        errors: list[str] = []
        for spec in specs:
            if not self._keys.get(spec.provider):
                errors.append(f"{spec.model}: no key")
                continue
            key = cache_key(spec)
            started = time.monotonic()
            try:
                data, tin, tout = self._call(spec, system, user, schema, max_output_tokens)
                if validate is not None:
                    validate(data)
            except (ProviderError, LlmError, ValueError, KeyError) as exc:
                ms = int((time.monotonic() - started) * 1000)
                self._log(
                    task, tier, spec, prompt_version, input_hash, 0, 0, ms, False, False, str(exc)
                )
                errors.append(f"{spec.model}: {exc}")
                continue
            ms = int((time.monotonic() - started) * 1000)
            self._store.put(key, data)
            self._log(
                task, tier, spec, prompt_version, input_hash, tin, tout, ms, False, True, None
            )
            return LlmResult(data, spec.model, spec.provider, tin, tout, ms, False)
        raise LlmError(f"{task}: every model failed: {'; '.join(errors)[:800]}")

    def _call(
        self,
        spec: ModelSpec,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int,
    ) -> tuple[Any, int, int]:
        for attempt in range(self._retries + 1):
            try:
                if spec.provider == "gemini":
                    return self._gemini(spec, system, user, schema, max_output_tokens)
                if spec.provider == "groq":
                    return self._groq(spec, system, user, schema, max_output_tokens)
                raise LlmError(f"unknown provider {spec.provider}")
            except ProviderError as exc:
                if exc.status not in RETRYABLE or attempt == self._retries:
                    raise
                time.sleep(2.0 * (attempt + 1) ** 2)
        raise LlmError("unreachable")

    def _gemini(
        self, spec: ModelSpec, system: str, user: str, schema: Mapping[str, Any], max_out: int
    ) -> tuple[Any, int, int]:
        config: dict[str, Any] = {
            "temperature": 0,
            "maxOutputTokens": max_out,
            "responseMimeType": "application/json",
            "responseJsonSchema": schema,
        }
        if spec.reasoning:
            config["thinkingConfig"] = {"thinkingLevel": spec.reasoning}
        out = self._post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{spec.model}:generateContent",
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": config,
            },
            {"x-goog-api-key": self._keys["gemini"] or ""},
            self._timeout,
        )
        cand = (out.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text.strip():
            raise LlmError(f"empty answer (finish: {cand.get('finishReason')})")
        usage = out.get("usageMetadata") or {}
        tokens_out = int(usage.get("candidatesTokenCount") or 0) + int(
            usage.get("thoughtsTokenCount") or 0
        )
        return json.loads(text), int(usage.get("promptTokenCount") or 0), tokens_out

    def _groq(
        self, spec: ModelSpec, system: str, user: str, schema: Mapping[str, Any], max_out: int
    ) -> tuple[Any, int, int]:
        body: dict[str, Any] = {
            "model": spec.model,
            "temperature": 0,
            "max_completion_tokens": max_out,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "answer", "schema": schema, "strict": False},
            },
        }
        if spec.reasoning:
            body["reasoning_effort"] = spec.reasoning
        out = self._post(
            "https://api.groq.com/openai/v1/chat/completions",
            body,
            {"Authorization": f"Bearer {self._keys['groq']}"},
            self._timeout,
        )
        text = out["choices"][0]["message"].get("content") or ""
        if not text.strip():
            raise LlmError("empty answer")
        usage = out.get("usage") or {}
        return (
            json.loads(text),
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
        )

    def _log(
        self,
        task: str,
        tier: str,
        spec: ModelSpec,
        prompt_version: str,
        input_hash: str,
        tokens_in: int,
        tokens_out: int,
        latency_ms: int,
        cache_hit: bool,
        ok: bool,
        error: str | None,
    ) -> None:
        self._store.log(
            {
                "task": task,
                "tier": tier,
                "provider": spec.provider,
                "model": spec.model,
                "prompt_version": prompt_version,
                "input_hash": input_hash,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency_ms": latency_ms,
                "cache_hit": cache_hit,
                "shadow_cost_usd": shadow_cost(spec.model, tokens_in, tokens_out),
                "ok": ok,
                "error": (error or "")[:500] or None,
            }
        )


class DbStore:
    """Cache and call log in Postgres (llm_cache, llm_calls)."""

    def __init__(self, url: str):
        self._url = url

    def get(self, key: str) -> Any | None:
        from finn.core.db import connect, fetch_all

        with connect(self._url) as conn:
            rows = fetch_all(conn, "select output from llm_cache where key = %s", [key])
        return rows[0]["output"] if rows else None

    def put(self, key: str, output: Any) -> None:
        from finn.core.db import Jsonb, connect, fetch_all

        with connect(self._url) as conn:
            fetch_all(
                conn,
                "insert into llm_cache (key, output) values (%s, %s)"
                " on conflict (key) do update set output = excluded.output",
                [key, Jsonb(output)],
            )

    def log(self, row: Mapping[str, Any]) -> None:
        from finn.core.db import connect, fetch_all

        cols = list(row)
        placeholders = ", ".join(["%s"] * len(cols))
        with connect(self._url) as conn:
            fetch_all(
                conn,
                f"insert into llm_calls ({', '.join(cols)}) values ({placeholders})",
                [row[c] for c in cols],
            )
