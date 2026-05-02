URGENCY_KEYWORDS = [
    "breaking", "urgent", "share before deleted", "they don't want you to know",
    "wake up", "share now", "delete soon", "they're hiding", "cover up",
    "before it's too late",
]


def check_urgency(text: str | None) -> bool:
    if not text:
        return False

    lower = text.lower()
    if any(kw in lower for kw in URGENCY_KEYWORDS):
        return True

    words = text.split()
    if len(words) >= 5:
        caps_words = sum(1 for w in words if w.isupper() and len(w) > 1)
        if caps_words / len(words) > 0.4:
            return True

    if text.count("!") >= 3:
        return True

    return False


def combine_urgency(rules_result: bool, llm_result: bool) -> bool:
    return rules_result or llm_result
