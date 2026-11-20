from decimal import Decimal

from app.services.ai_pricing import (
    claude_cost_micros,
    claude_reservation_micros,
    embedding_cost_micros,
    embedding_reservation_micros,
    estimate_tokens,
    is_priced,
    usd_to_micros,
)


def test_sonnet_reservation_is_input_at_2_and_output_at_10_micros_per_token():
    assert claude_reservation_micros("claude-sonnet-5-5", input_tokens=8_000, max_tokens=4_000) == 56_000


def test_sonnet_cost_from_usage():
    assert claude_cost_micros("claude-sonnet-5-5", input_tokens=1_000, output_tokens=200) == 4_000


def test_cache_tokens_are_priced():
    # 1,000 cache reads at 0.10 + 1,000 cache writes at 2.50 micros per token.
    assert (
        claude_cost_micros(
            "claude-sonnet-5-5",
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=1_000,
            cache_write_tokens=1_000,
        )
        == 2_600
    )


def test_an_unknown_model_is_priced_at_the_dearest_row(caplog):
    assert claude_cost_micros("claude-unknown", input_tokens=1_000, output_tokens=0) == 5_000
    assert not is_priced("claude-unknown")
    assert "claude-unknown" in caplog.text


def test_is_priced_for_known_models():
    assert is_priced("claude-sonnet-5-5") and is_priced("text-embedding-3-small")


def test_estimate_is_two_bytes_a_token():
    assert estimate_tokens("x" * 2_001) == 1_001


def test_embedding_costs():
    assert embedding_reservation_micros("text-embedding-3-small", ["x" * 2_000]) == 20
    assert embedding_cost_micros("text-embedding-3-small", 6_000) == 120
    assert embedding_reservation_micros("text-embedding-3-small", [""]) == 1


def test_usd_to_micros_rounds_up():
    assert usd_to_micros(Decimal("0.15")) == 150_000
    assert usd_to_micros(Decimal("0.0000001")) == 1


def test_cache_prices_are_explicit_per_row():
    # Opus 5.5: 1,000 cache reads at 0.20 + 1,000 cache writes at 5.00 micros per token.
    assert (
        claude_cost_micros(
            "claude-opus-5-5",
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=1_000,
            cache_write_tokens=1_000,
        )
        == 5_200
    )
    # Haiku 5.5: 10,000 cache reads at 0.01 + 8,000 cache writes at 0.125.
    assert (
        claude_cost_micros(
            "claude-haiku-5-5",
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=10_000,
            cache_write_tokens=8_000,
        )
        == 1_100
    )
