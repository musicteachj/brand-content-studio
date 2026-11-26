"""The seed's corpus vectors come from a checked-in fixture, so seeding makes no paid call."""
import pytest

from app.config import settings
from seed.seed_demo import (
    CORPUS,
    EMBEDDINGS_FIXTURE,
    SeedError,
    chunk_key,
    corpus_chunks,
    load_embeddings_fixture,
    write_embeddings_fixture,
)

IDS_A = {f: f"asset-{i}" for i, (f, _, _) in enumerate(CORPUS)}
IDS_B = {f: f"other-{i}" for i, (f, _, _) in enumerate(CORPUS)}


def test_chunk_key_is_stable_and_corpus_chunks_are_deterministic():
    assert chunk_key("hello") == chunk_key("hello")
    assert chunk_key("hello") != chunk_key("hello!")
    assert len(chunk_key("hello")) == 64  # sha256 hex
    a = corpus_chunks("ns-a", IDS_A)
    b = corpus_chunks("ns-b", IDS_B)
    assert a and [c["text"] for c in a] == [c["text"] for c in b]
    assert {c["metadata"]["filename"] for c in a} == {f for f, _, _ in CORPUS}


def test_every_corpus_chunk_has_a_fixture_embedding():
    fixture = load_embeddings_fixture()
    missing = [c["id"] for c in corpus_chunks("ns", IDS_A) if chunk_key(c["text"]) not in fixture]
    assert not missing, "corpus or chunker changed: run python -m seed.build_embeddings_fixture"
    assert all(len(v) == settings.embedding_dim for v in fixture.values())


def test_fixture_round_trips_and_checks_model_and_dim(tmp_path):
    path = tmp_path / "f.json"
    vec = [0.25] * settings.embedding_dim
    write_embeddings_fixture({"k": vec}, path)
    assert load_embeddings_fixture(path) == {"k": vec}
    path.write_text(path.read_text().replace(settings.embedding_model, "other-model"))
    with pytest.raises(SeedError):
        load_embeddings_fixture(path)


def test_checked_in_fixture_is_small():
    assert EMBEDDINGS_FIXTURE.stat().st_size < 500_000
