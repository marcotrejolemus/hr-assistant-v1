"""Pruebas de la detección y redacción de PII (datos ficticios)."""

import pytest

from app.pii import redact_pii


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        ("ana.ficticia@example.com", "email"),
        ("55 1234 5678", "phone"),
        ("+52 5512345678", "phone"),
        ("GOLA900101HDFRPN09", "curp"),
        ("GOLA900101AB1", "rfc"),
        ("4111 1111 1111 1111", "card"),
    ],
)
def test_each_pii_type_is_replaced_by_its_label(value, kind):
    """Cada tipo se reemplaza por ``[REDACTED:<tipo>]`` y se informa una vez."""
    result = redact_pii(f"Dato {value} fin")

    assert value not in result.text
    assert result.text == f"Dato [REDACTED:{kind}] fin"
    assert list(result.types) == [kind]
