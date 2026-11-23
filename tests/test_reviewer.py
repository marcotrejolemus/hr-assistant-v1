"""Pruebas del parseo estricto del veredicto del Reviewer."""

import pytest

from app.reviewer import parse_verdict

ISSUE = "menciona datos que no pidieron"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"verdict": "approve", "issues": []}', ("approve", [])),
        (f'{{"verdict": "reject", "issues": ["{ISSUE}"]}}', ("reject", [ISSUE])),
        ("this is not json", None),
        ('["approve"]', None),
        ('{"verdict": "maybe", "issues": []}', None),
        ('{"verdict": "approve"}', None),
        ('{"verdict": "approve", "issues": "none"}', None),
        ('{"verdict": "approve", "issues": [], "answer": "otra"}', None),
    ],
    ids=[
        "approve",
        "reject",
        "not_json",
        "not_an_object",
        "unknown_verdict",
        "missing_issues",
        "issues_not_a_list",
        "extra_field",
    ],
)
def test_only_a_strict_verdict_is_accepted(text, expected):
    """Un veredicto inválido o con campos extra lanza ``ValueError``.

    El Reviewer convierte ese error en ``review.status = "unavailable"``.
    """
    if expected is None:
        with pytest.raises(ValueError):
            parse_verdict(text)
        return
    verdict = parse_verdict(text)
    assert (verdict.verdict, list(verdict.issues)) == expected
