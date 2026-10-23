from unittest import mock

import pytest

from clients.exceptions import CityNotFoundError
from processing.service import build_city_summary


def test_builds_summary_in_documented_shape() -> None:
    with (
        mock.patch(
            "processing.service.get_weather",
            return_value={"city": "Moscow", "temp_c": -3.2, "description": "clear sky"},
        ),
        mock.patch("processing.service.get_rate", return_value=92.15) as get_rate,
    ):
        summary = build_city_summary("moscow")

    assert summary == {
        "city": "Moscow",
        "weather": {"temp_c": -3.2, "description": "clear sky", "warm_clothes": True},
        "rates": {"currency": "USD", "rate_to_rub": 92.15, "expensive": False},
    }
    get_rate.assert_called_once_with("USD", cache=None)


def test_rate_is_not_requested_when_city_is_unknown() -> None:
    with (
        mock.patch("processing.service.get_weather", side_effect=CityNotFoundError("X")),
        mock.patch("processing.service.get_rate") as get_rate,
        pytest.raises(CityNotFoundError),
    ):
        build_city_summary("X", "EUR")

    get_rate.assert_not_called()
