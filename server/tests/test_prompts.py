"""Prompt assembly: brand context is framed as data-not-instructions; voice
summary rides in the system header."""
from app.models.generation import Length, Tone
from app.prompts import text_post


def _chunk(text: str, kind: str = "posts", filename: str = "past-posts.md"):
    return {
        "id": "a:0",
        "text": text,
        "score": 0.9,
        "metadata": {"asset_kind": kind, "filename": filename, "chunk_index": 0},
    }


def test_system_includes_injection_defense_and_voice():
    system = text_post.build_system("Grounded, data-first voice.")
    assert "untrusted" in system.lower()
    assert "ignore" in system.lower()  # instruction to ignore embedded commands
    assert "Grounded, data-first voice." in system


def test_user_wraps_chunks_in_delimited_brand_context():
    user = text_post.build_user(
        "Write about hempcrete",
        Tone.default,
        Length.medium,
        [_chunk("Hempcrete sequesters carbon.")],
    )
    assert "<brand_context>" in user and "</brand_context>" in user
    assert "Hempcrete sequesters carbon." in user
    assert 'kind="posts"' in user
    assert "hempcrete" in user.lower()


def test_user_includes_tone_and_length_guidance():
    user = text_post.build_user("brief", Tone.technical, Length.short, [_chunk("x")])
    assert "50" in user  # short length guidance mentions the word range
    assert "technical" in user.lower() or "numbers" in user.lower()


def test_empty_context_is_marked():
    user = text_post.build_user("brief", Tone.default, Length.medium, [])
    assert "no brand material retrieved" in user
