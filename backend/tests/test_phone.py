"""Нормализация номеров телефона."""

import pytest

from app.core.exceptions import ValidationError
from app.shared.phone import mask_phone, normalize_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+77011234567", "+77011234567"),
        ("87011234567", "+77011234567"),
        ("7011234567", "+77011234567"),
        ("8 (701) 123-45-67", "+77011234567"),
        ("+7 701 123 45 67", "+77011234567"),
    ],
)
def test_normalize_accepts_common_formats(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["123", "", "+79161234567", "8701123456789", "не телефон"])
def test_normalize_rejects_invalid(raw: str) -> None:
    with pytest.raises(ValidationError):
        normalize_phone(raw)


def test_mask_hides_middle_digits() -> None:
    assert mask_phone("+77011234567") == "+7 701 ***-**-67"
