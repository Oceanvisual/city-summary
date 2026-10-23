from collections.abc import Iterator
from unittest import mock

import pytest

from clients import weather
from clients.exceptions import CityNotFoundError, InvalidResponseError

GEOCODING_OK = {
    "results": [
        {"name": "Moscow", "latitude": 55.75, "longitude": 37.62, "country": "Russia", "id": 1}
    ],
    "generationtime_ms": 0.3,
}
FORECAST_OK = {
    "latitude": 55.78,
    "current_units": {"temperature_2m": "°C"},
    "current": {"time": "2026-10-15T13:00", "temperature_2m": -3.2, "weather_code": 0},
}


@pytest.fixture
def get_json() -> Iterator[mock.MagicMock]:
    with mock.patch("clients.weather.get_json") as patched:
        yield patched


def test_geocodes_then_fetches_current_weather(get_json: mock.MagicMock) -> None:
    get_json.side_effect = [GEOCODING_OK, FORECAST_OK]

    result = weather.get_weather("moscow")

    assert result == {"city": "Moscow", "temp_c": -3.2, "description": "clear sky"}
    geo_call, forecast_call = get_json.call_args_list
    assert geo_call.args == (weather.GEOCODING_URL,)
    assert geo_call.kwargs["params"]["name"] == "moscow"
    assert forecast_call.args == (weather.FORECAST_URL,)
    assert forecast_call.kwargs["params"]["latitude"] == 55.75
    assert forecast_call.kwargs["params"]["longitude"] == 37.62


def test_unknown_city_raises_not_found(get_json: mock.MagicMock) -> None:
    get_json.return_value = {"generationtime_ms": 0.2}  # так Open-Meteo отвечает «ничего нет»

    with pytest.raises(CityNotFoundError, match="Atlantis"):
        weather.get_weather("Atlantis")

    get_json.assert_called_once()  # прогноз даже не запрашиваем


def test_unknown_weather_code_gives_empty_description(get_json: mock.MagicMock) -> None:
    forecast = {"current": {"temperature_2m": 1.0, "weather_code": 42}}
    get_json.side_effect = [GEOCODING_OK, forecast]

    assert weather.get_weather("Moscow")["description"] == ""


@pytest.mark.parametrize(
    "forecast",
    [
        {},
        {"current": {"weather_code": 0}},
        {"current": {"temperature_2m": "-3.2", "weather_code": 0}},
        {"current": {"temperature_2m": None, "weather_code": 0}},
        {"current": {"temperature_2m": -3.2, "weather_code": "clear"}},
        [],
    ],
    ids=["empty", "no_temperature", "temp_as_string", "temp_null", "code_as_string", "list"],
)
def test_malformed_forecast_is_invalid_response(get_json: mock.MagicMock, forecast: object) -> None:
    get_json.side_effect = [GEOCODING_OK, forecast]

    with pytest.raises(InvalidResponseError, match="Open-Meteo forecast"):
        weather.get_weather("Moscow")


@pytest.mark.parametrize(
    "geocoding",
    [
        {"results": [{"name": "Moscow", "latitude": 55.75}]},
        {"results": [{"name": "Moscow", "latitude": 155.0, "longitude": 37.62}]},
        {"results": "Moscow"},
    ],
    ids=["no_longitude", "latitude_out_of_range", "results_not_list"],
)
def test_malformed_geocoding_is_invalid_response(
    get_json: mock.MagicMock, geocoding: object
) -> None:
    get_json.return_value = geocoding

    with pytest.raises(InvalidResponseError, match="Open-Meteo geocoding"):
        weather.get_weather("Moscow")
