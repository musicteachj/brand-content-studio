"""Rebuild seed/fixtures/verdure_embeddings.json from the Verdure corpus.

This is a PAID run: it embeds every corpus chunk with OpenAI (about 6,000 tokens at
$0.02 per million, well under a cent). Run it only when the corpus or the chunker
changes (tests/test_seed_embeddings_fixture.py fails until you do), with a development
OpenAI key, never a production key:

    cd server && .venv/bin/python -m seed.build_embeddings_fixture --yes

Without --yes it only prints the token estimate and cost, and makes no call.
"""
import argparse
import math
import sys
from decimal import Decimal

from app.config import settings
from app.rag.embeddings import OpenAIEmbedder
from app.services.ai_pricing import EMBEDDING_PRICES
from seed.seed_demo import (
    CORPUS,
    EMBEDDINGS_FIXTURE,
    chunk_key,
    corpus_chunks,
    write_embeddings_fixture,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="make the paid OpenAI call")
    args = parser.parse_args(argv)

    chunks = corpus_chunks("fixture", {filename: f"asset-{i}" for i, (filename, _, _) in enumerate(CORPUS)})
    unique = {chunk_key(c["text"]): c["text"] for c in chunks}
    texts = list(unique.values())
    tokens = sum(math.ceil(len(t.encode("utf-8")) / 2) for t in texts)  # the ledger's safe bound
    cost = Decimal(tokens) * EMBEDDING_PRICES[settings.embedding_model] / Decimal(1_000_000)
    print(
        f"{len(texts)} unique chunks, at most {tokens} tokens, "
        f"{settings.embedding_model} at up to ${cost:.6f}"
    )
    if not args.yes:
        print("Refusing to call OpenAI without --yes. Nothing was sent.", file=sys.stderr)
        return 2
    if not settings.openai_api_key.get_secret_value():
        print("OPENAI_API_KEY is not set.", file=sys.stderr)
        return 1

    vectors, used = OpenAIEmbedder().embed_with_usage(texts)
    write_embeddings_fixture(dict(zip(unique.keys(), vectors, strict=True)))
    print(f"Wrote {EMBEDDINGS_FIXTURE} ({used} tokens billed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
