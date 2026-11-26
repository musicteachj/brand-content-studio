"""post-stream parsing into the persisted TextOutput shape."""
from app.services.ai_service import parse_post


def test_parse_post_extracts_hashtags_and_counts():
    text = "  A grounded post about embodied carbon.\n\n#EmbodiedCarbon #Hempcrete #EmbodiedCarbon  "
    out = parse_post(text)
    assert out["post_text"].startswith("A grounded post")
    assert out["hashtags"] == ["#EmbodiedCarbon", "#Hempcrete"]  # deduped, order-preserved
    assert out["char_count"] == len(out["post_text"])


def test_parse_post_no_hashtags():
    out = parse_post("Just a plain post.")
    assert out["hashtags"] == []
    assert out["char_count"] == len("Just a plain post.")
