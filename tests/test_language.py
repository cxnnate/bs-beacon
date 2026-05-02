from src.processing.language import detect_language


def test_detects_english():
    assert detect_language("Scientists published a new study on vaccine safety today.") == "en"


def test_detects_spanish():
    assert detect_language("El gobierno aprobó una nueva ley sobre vacunas obligatorias.") == "es"


def test_detects_russian():
    assert detect_language("Правительство одобрило новый закон об обязательной вакцинации.") == "ru"


def test_short_text_returns_unknown():
    assert detect_language("hi") == "unknown"


def test_empty_string_returns_unknown():
    assert detect_language("") == "unknown"


def test_none_returns_unknown():
    assert detect_language(None) == "unknown"
