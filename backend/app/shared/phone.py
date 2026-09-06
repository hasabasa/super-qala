"""Нормализация казахстанских номеров телефона.

В базе номер хранится в одном каноническом виде: +77XXXXXXXXX.
Пользователь может ввести его как угодно — с восьмёркой, скобками, пробелами.
"""

import re

from app.core.exceptions import ValidationError

_DIGITS = re.compile(r"\D")


def normalize_phone(raw: str) -> str:
    """Приводит номер к виду +77XXXXXXXXX или бросает ValidationError."""
    digits = _DIGITS.sub("", raw)

    if len(digits) == 10 and digits.startswith("7"):
        digits = "7" + digits
    elif len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]

    if len(digits) != 11 or not digits.startswith("77"):
        raise ValidationError("Некорректный номер телефона. Ожидается казахстанский мобильный")

    return "+" + digits


def mask_phone(phone: str) -> str:
    """+77011234567 → +7 701 ***-**-67"""
    if len(phone) != 12:
        return phone
    return f"+7 {phone[2:5]} ***-**-{phone[-2:]}"
