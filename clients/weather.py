"""Клиент Open-Meteo: геокодинг города, затем текущая погода по координатам."""

from typing import Annotated, Final, TypedDict

import structlog
from pydantic import Field

from clients.exceptions import CityNotFoundError
from clients.http import get_json
from clients.validation import ResponseModel, validate_payload

log = structlog.get_logger(__name__)

GEOCODING_URL: Final = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL: Final = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo отдаёт погоду кодом WMO; текст — по таблице из документации API.
WMO_DESCRIPTIONS: Final[dict[int, str]] = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snow fall",
    73: "moderate snow fall",
    75: "heavy snow fall",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


class WeatherData(TypedDict):
    city: str
    """Название города из геокодера (нормализованное: «moscow» → «Moscow»)."""
    temp_c: float
    description: str
    """Пустая строка, если код погоды неизвестен."""


class _Place(ResponseModel):
    name: Annotated[str, Field(min_length=1)]
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]


class _GeocodingResponse(ResponseModel):
    # Если ничего не найдено, Open-Meteo просто не присылает ключ results.
    results: list[_Place] = Field(default_factory=list)


class _Current(ResponseModel):
    temperature_2m: float
    weather_code: int


class _ForecastResponse(ResponseModel):
    current: _Current


def get_weather(city: str) -> WeatherData:
    """Текущая погода в городе.

    Raises:
        CityNotFoundError: геокодер не знает такой город.
        ServiceUnavailableError, InvalidResponseError, UpstreamHTTPError: проблемы Open-Meteo.
    """
    place = _geocode(city)
    payload = get_json(
        FORECAST_URL,
        params={
            "latitude": place.latitude,
            "longitude": place.longitude,
            "current": "temperature_2m,weather_code",
        },
    )
    current = validate_payload(_ForecastResponse, payload, source="Open-Meteo forecast").current
    log.info("weather_fetched", city=place.name, temp_c=current.temperature_2m)
    return {
        "city": place.name,
        "temp_c": current.temperature_2m,
        "description": WMO_DESCRIPTIONS.get(current.weather_code, ""),
    }


def _geocode(city: str) -> _Place:
    payload = get_json(
        GEOCODING_URL,
        params={"name": city, "count": 1, "language": "en", "format": "json"},
    )
    response = validate_payload(_GeocodingResponse, payload, source="Open-Meteo geocoding")
    if not response.results:
        raise CityNotFoundError(city)
    return response.results[0]
