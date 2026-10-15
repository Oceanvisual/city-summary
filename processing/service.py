"""Сборка сводки по городу из ответов клиентов."""

from typing import TypedDict

import structlog

from clients.cache import FileTTLCache
from clients.rates import get_rate
from clients.weather import get_weather
from processing.preprocessing import (
    RatesSummary,
    WeatherSummary,
    preprocess_rate,
    preprocess_weather,
)

log = structlog.get_logger(__name__)


class CitySummary(TypedDict):
    city: str
    weather: WeatherSummary
    rates: RatesSummary


def build_city_summary(
    city: str,
    currency: str = "USD",
    *,
    rate_cache: FileTTLCache | None = None,
) -> CitySummary:
    """Собирает погоду и курс в единую сводку с флагами предобработки.

    Raises:
        NotFoundError: город или код валюты не найдены.
        ExternalServiceError: внешний сервис недоступен или ответил некорректно.
    """
    weather = get_weather(city)
    rate = get_rate(currency, cache=rate_cache)
    summary: CitySummary = {
        "city": weather["city"],
        "weather": preprocess_weather(weather["temp_c"], weather["description"]),
        "rates": preprocess_rate(currency, rate),
    }
    log.info("summary_built", city=summary["city"], currency=summary["rates"]["currency"])
    return summary
