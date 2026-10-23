"""Правила предобработки: флаги и нормализация, зависящие от полученных данных.

Флаги считаются по уже округлённым значениям, чтобы вывод не противоречил сам себе
(иначе -0.04 °C напечаталось бы как «0.0°C» с флагом «тёплая одежда: да»).
"""

from typing import Final, TypedDict

COLD_THRESHOLD_C: Final = 0.0
"""Ниже этой температуры нужна тёплая одежда."""

EXPENSIVE_RATE_THRESHOLD_RUB: Final = 100.0
"""Выше этого курса валюта считается дорогой."""

DEFAULT_DESCRIPTION: Final = "нет данных"
"""Подставляется, если сервис не дал описания погоды."""

TEMP_DIGITS: Final = 1
RATE_DIGITS: Final = 2
SMALL_RATE_SIGNIFICANT_DIGITS: Final = 4


class WeatherSummary(TypedDict):
    temp_c: float
    description: str
    warm_clothes: bool


class RatesSummary(TypedDict):
    currency: str
    rate_to_rub: float
    expensive: bool


def round_temperature(temp_c: float) -> float:
    # + 0.0 превращает -0.0 в 0.0, чтобы не печатать «-0.0°C».
    return round(temp_c, TEMP_DIGITS) + 0.0


def round_rate(rate: float) -> float:
    """Курс ≥ 1 — до копеек; дешёвые валюты (KZT, JPY, ...) — 4 значащие цифры, иначе 0.0."""
    if rate >= 1:
        return round(rate, RATE_DIGITS)
    return float(f"{rate:.{SMALL_RATE_SIGNIFICANT_DIGITS}g}")


def needs_warm_clothes(temp_c: float) -> bool:
    return temp_c < COLD_THRESHOLD_C


def is_expensive(rate_to_rub: float) -> bool:
    return rate_to_rub > EXPENSIVE_RATE_THRESHOLD_RUB


def normalize_description(description: str) -> str:
    """Схлопывает пробелы; пустое описание заменяет значением по умолчанию."""
    return " ".join(description.split()) or DEFAULT_DESCRIPTION


def preprocess_weather(temp_c: float, description: str) -> WeatherSummary:
    temp = round_temperature(temp_c)
    return {
        "temp_c": temp,
        "description": normalize_description(description),
        "warm_clothes": needs_warm_clothes(temp),
    }


def preprocess_rate(currency: str, rate_to_rub: float) -> RatesSummary:
    rate = round_rate(rate_to_rub)
    return {
        "currency": currency.strip().upper(),
        "rate_to_rub": rate,
        "expensive": is_expensive(rate),
    }
