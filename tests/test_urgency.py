from src.processing.urgency import check_urgency, combine_urgency


def test_breaking_keyword_flagged():
    assert check_urgency("BREAKING: New vaccine linked to deaths, share now!") is True


def test_urgent_keyword_flagged():
    assert check_urgency("URGENT: They are hiding this from you.") is True


def test_share_before_deleted_flagged():
    assert check_urgency("Share before they delete this. They don't want you to know.") is True


def test_high_caps_ratio_flagged():
    assert check_urgency("THIS VACCINE IS DEADLY AND THEY ARE LYING TO US ALL") is True


def test_excessive_exclamation_flagged():
    assert check_urgency("Wake up people!!! Share this now!!! They are hiding it!!!") is True


def test_calm_message_not_flagged():
    assert check_urgency("Scientists published a new study on mRNA vaccine efficacy.") is False


def test_empty_message_not_flagged():
    assert check_urgency("") is False


def test_combine_urgency_rules_true():
    assert combine_urgency(rules_result=True, llm_result=False) is True


def test_combine_urgency_llm_true():
    assert combine_urgency(rules_result=False, llm_result=True) is True


def test_combine_urgency_both_false():
    assert combine_urgency(rules_result=False, llm_result=False) is False
