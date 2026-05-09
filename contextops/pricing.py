"""Anthropic pricing constants and dollar-cost helpers.

All prices are dollars per **million** tokens, taken from Anthropic's public
pricing page. Numbers are conservative; they're meant to be representative,
not bill-accurate. Override at runtime via `Pricing.from_model(...)` if you
need to track promotional rates.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pricing:
    """Per-million-token prices in USD."""

    input_per_mtok: float
    output_per_mtok: float
    cache_write_per_mtok: float  # 5-minute ephemeral writes (1.25× input)
    cache_read_per_mtok: float   # cache hits (0.1× input)

    @classmethod
    def for_model(cls, model: str | None) -> "Pricing":
        if not model:
            return _DEFAULT
        m = model.lower()
        for prefix, price in _BY_PREFIX:
            if m.startswith(prefix):
                return price
        return _DEFAULT

    def dollars(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_write_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> float:
        return (
            input_tokens * self.input_per_mtok
            + output_tokens * self.output_per_mtok
            + cache_write_tokens * self.cache_write_per_mtok
            + cache_read_tokens * self.cache_read_per_mtok
        ) / 1_000_000


# Representative public prices (USD per 1M tokens) for the Claude 4.x family.
# Source: https://www.anthropic.com/pricing  (approximate; update as needed).
OPUS_4 = Pricing(
    input_per_mtok=15.0,
    output_per_mtok=75.0,
    cache_write_per_mtok=18.75,
    cache_read_per_mtok=1.50,
)
SONNET_4 = Pricing(
    input_per_mtok=3.0,
    output_per_mtok=15.0,
    cache_write_per_mtok=3.75,
    cache_read_per_mtok=0.30,
)
HAIKU_4 = Pricing(
    input_per_mtok=1.0,
    output_per_mtok=5.0,
    cache_write_per_mtok=1.25,
    cache_read_per_mtok=0.10,
)

_DEFAULT = SONNET_4

_BY_PREFIX: list[tuple[str, Pricing]] = [
    ("claude-opus", OPUS_4),
    ("claude-sonnet", SONNET_4),
    ("claude-haiku", HAIKU_4),
    # legacy id forms
    ("claude-3-opus", OPUS_4),
    ("claude-3-5-sonnet", SONNET_4),
    ("claude-3-5-haiku", HAIKU_4),
    ("claude-3-haiku", HAIKU_4),
]


def estimate_tokens(text: str) -> int:
    """Cheap, dependency-free token estimator: ~4 chars per token.

    If the `anthropic` SDK is installed, callers can swap in its tokenizer,
    but ContextOps deliberately keeps this offline by default.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)
