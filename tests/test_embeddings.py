from src.processing.embeddings import Embedder


def test_embedding_has_correct_dimensions():
    embedder = Embedder()
    vec = embedder.embed("The FDA approved a new vaccine for COVID-19.")
    assert len(vec) == 768


def test_embedding_is_list_of_floats():
    embedder = Embedder()
    vec = embedder.embed("The FDA approved a new vaccine for COVID-19.")
    assert isinstance(vec, list)
    assert all(isinstance(x, float) for x in vec)


def test_similar_texts_high_cosine_similarity():
    embedder = Embedder()
    v1 = embedder.embed("The FDA approved a new COVID-19 vaccine.")
    v2 = embedder.embed("FDA has given approval to a COVID-19 vaccine.")
    assert embedder.cosine_similarity(v1, v2) > 0.85


def test_different_texts_below_dedup_threshold():
    # e5 models compress cosine into a high range (~0.7 floor for unrelated
    # texts), so "low" similarity means below the 0.88 candidate threshold.
    embedder = Embedder()
    v1 = embedder.embed("The FDA approved a new COVID-19 vaccine.")
    v2 = embedder.embed("Stock markets fell sharply on Friday amid recession fears.")
    assert embedder.cosine_similarity(v1, v2) < 0.85


def test_crosslingual_same_claim_above_dedup_threshold():
    embedder = Embedder()
    v1 = embedder.embed("The FDA approved a new COVID-19 vaccine.")
    v2 = embedder.embed("La FDA aprobó una nueva vacuna contra el COVID-19.")
    assert embedder.cosine_similarity(v1, v2) > 0.88


def test_same_text_similarity_is_one():
    embedder = Embedder()
    text = "The FDA approved a new COVID-19 vaccine."
    v1 = embedder.embed(text)
    v2 = embedder.embed(text)
    assert abs(embedder.cosine_similarity(v1, v2) - 1.0) < 0.001


def test_embed_empty_string_raises():
    import pytest
    embedder = Embedder()
    with pytest.raises(ValueError, match="non-empty"):
        embedder.embed("")


def test_embed_whitespace_only_raises():
    import pytest
    embedder = Embedder()
    with pytest.raises(ValueError, match="non-empty"):
        embedder.embed("   ")
