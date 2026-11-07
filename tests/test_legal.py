from escapehatch.legal import (
    CA_ARL,
    CNIL_GUIDELINES,
    DSA_25,
    EPRIVACY_5_3,
    FR_L215_1_1,
    GDPR_7_3,
    UCPD,
    US_ROSCA,
    applicable_refs,
)
from escapehatch.prompts import Task


def test_baseline_refs_for_refuse_cookies():
    refs = applicable_refs(Task.REFUSE_COOKIES, [])
    assert refs == [EPRIVACY_5_3, CNIL_GUIDELINES, GDPR_7_3]


def test_pattern_refs_appended_and_deduped():
    # asymmetric_choice -> DSA_25; confirmshaming -> DSA_25 + UCPD
    refs = applicable_refs(Task.REFUSE_COOKIES, ["asymmetric_choice", "confirmshaming"])
    assert refs == [EPRIVACY_5_3, CNIL_GUIDELINES, GDPR_7_3, DSA_25, UCPD]
    assert len(refs) == len(set(refs))


def test_task_without_baseline_gets_only_pattern_refs():
    refs = applicable_refs(Task.ACCEPT_COOKIES, ["forced_action"])
    assert refs == [UCPD]


def test_cancel_subscription_baseline_and_patterns():
    refs = applicable_refs(Task.CANCEL_SUBSCRIPTION, ["obstruction", "sneaking"])
    # obstruction -> (DSA_25, UCPD); sneaking -> (UCPD,) — dedup keeps order
    assert refs == [FR_L215_1_1, US_ROSCA, CA_ARL, DSA_25, UCPD]


def test_unknown_pattern_ignored():
    refs = applicable_refs(Task.UNSUBSCRIBE, ["bogus_pattern"])
    assert len(refs) == 2  # FR_L34_5 + US_CAN_SPAM baseline only
