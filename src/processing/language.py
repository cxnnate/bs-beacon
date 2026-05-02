from langdetect import detect, LangDetectException


def detect_language(text: str | None) -> str:
    if not text or len(text.strip()) < 20:
        return "unknown"
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"
