"""What a model call costs, in integer micro-dollars (1 micro = $0.000001).

A price in dollars per million tokens is numerically the same as micro-dollars per token, so
`tokens x price` is already in micros. Amounts round up (`ROUND_CEILING`): the ledger may
overstate a cost by under one micro, never understate it.

Prices are per million tokens: Sonnet 5.5 $2 input, $10 output, $0.10 cache read; Opus 5.5
$4 / $20; Haiku 5.5 $0.10 / $0.50; Opus 5 and 4.8 $5 / $25; `text-embedding-3-small` $0.02.
Every row lists its cache read and 5-minute cache write price explicitly (Sonnet 5.5 $0.10 and
$2.50, Opus 5.5 $0.20 and $5.00, Haiku 5.5 $0.01 and $0.125, Opus 5 and 4.8 $0.50 and $6.25);
the Haiku and Opus 5 / 4.8 cache reads come from the reference. Reference: open-door/apps/api/app/ai/pricing.py.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

logger = logging.getLogger(__name__)

# Open Door's safe bound: a token is never fewer than two UTF-8 bytes of text, so
# ceil(bytes / 2) overestimates and the reservation errs on the safe side.
BYTES_PER_TOKEN = 2
IMAGE_TOKEN_BOUND = 5_000
SCHEMA_OVERHEAD_TOKENS = 500


@dataclass(frozen=True)
class ClaudePrice:
    """Dollars per million tokens (equal to micros per token)."""

    input: Decimal
    output: Decimal
    cache_read: Decimal
    cache_write: Decimal


def _claude(input_usd: str, output_usd: str, cache_read_usd: str, cache_write_usd: str) -> ClaudePrice:
    return ClaudePrice(
        input=Decimal(input_usd),
        output=Decimal(output_usd),
        cache_read=Decimal(cache_read_usd),
        cache_write=Decimal(cache_write_usd),
    )


# Dollars per million tokens: input, output, cache read, 5-minute cache write.
CLAUDE_PRICES: dict[str, ClaudePrice] = {
    "claude-sonnet-5-5": _claude("2", "10", "0.10", "2.50"),
    "claude-opus-5-5": _claude("4", "20", "0.20", "5.00"),
    "claude-haiku-5-5": _claude("0.10", "0.50", "0.01", "0.125"),
    "claude-opus-5": _claude("5", "25", "0.50", "6.25"),
    "claude-opus-4-8": _claude("5", "25", "0.50", "6.25"),
}
EMBEDDING_PRICES: dict[str, Decimal] = {"text-embedding-3-small": Decimal("0.02")}

_DEAREST = max(CLAUDE_PRICES.values(), key=lambda p: (p.output, p.input))


def usd_to_micros(usd: Decimal) -> int:
    return int((usd * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


def _ceil(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def estimate_tokens(text: str) -> int:
    return -(-len(text.encode("utf-8")) // BYTES_PER_TOKEN)


def is_priced(model: str) -> bool:
    return model in CLAUDE_PRICES or model in EMBEDDING_PRICES


def _claude_price(model: str) -> ClaudePrice:
    price = CLAUDE_PRICES.get(model)
    if price is None:
        logger.warning("No price for model %r; using the dearest row", model)
        return _DEAREST
    return price


def claude_reservation_micros(model: str, *, input_tokens: int, max_tokens: int) -> int:
    """The worst case for one call: every input token at the input price, and the output
    cap at the output price."""
    price = _claude_price(model)
    return _ceil(input_tokens * price.input + max_tokens * price.output)


def claude_cost_micros(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> int:
    price = _claude_price(model)
    return _ceil(
        input_tokens * price.input
        + output_tokens * price.output
        + cache_read_tokens * price.cache_read
        + cache_write_tokens * price.cache_write
    )


def _embedding_price(model: str) -> Decimal:
    price = EMBEDDING_PRICES.get(model)
    if price is None:
        logger.warning("No price for embedding model %r; using the dearest row", model)
        return max(EMBEDDING_PRICES.values())
    return price


def embedding_reservation_micros(model: str, texts: Sequence[str]) -> int:
    tokens = sum(estimate_tokens(t) for t in texts)
    return max(_ceil(tokens * _embedding_price(model)), 1)


def embedding_cost_micros(model: str, tokens: int) -> int:
    return _ceil(tokens * _embedding_price(model))
