import pytest

from processing import preprocessing as pp


@pytest.mark.parametrize(
    ("temp_c", "expected"),
    [(-3.2, True), (-0.1, True), (-0.04, False), (0.0, False), (12.5, False)],
)
def test_warm_clothes_below_zero(temp_c: float, expected: bool) -> None:
    # -0.04 округляется до 0.0 — флаг согласован с тем, что видит пользователь.
    assert pp.preprocess_weather(temp_c, "clear sky")["warm_clothes"] is expected


@pytest.mark.parametrize(
    ("rate", "expected"),
    [(92.15, False), (100.0, False), (100.004, False), (100.01, True), (105.3, True)],
)
def test_expensive_above_hundred(rate: float, expected: bool) -> None:
    assert pp.preprocess_rate("USD", rate)["expensive"] is expected


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("clear sky", "clear sky"),
        ("  partly   cloudy ", "partly cloudy"),
        ("", pp.DEFAULT_DESCRIPTION),
        ("   ", pp.DEFAULT_DESCRIPTION),
    ],
)
def test_description_normalized_with_default(description: str, expected: str) -> None:
    assert pp.preprocess_weather(1.0, description)["description"] == expected


@pytest.mark.parametrize(
    ("temp_c", "expected"),
    [(-3.24, -3.2), (9.05, 9.1), (-0.04, 0.0)],
)
def test_temperature_rounded_to_tenths(temp_c: float, expected: float) -> None:
    assert pp.preprocess_weather(temp_c, "x")["temp_c"] == expected


def test_negative_zero_is_normalized() -> None:
    assert str(pp.round_temperature(-0.04)) == "0.0"


@pytest.mark.parametrize(
    ("rate", "expected"),
    [(83.9234, 83.92), (1.0, 1.0), (0.186254, 0.1863), (0.00512345, 0.005123)],
)
def test_rate_precision_depends_on_magnitude(rate: float, expected: float) -> None:
    assert pp.preprocess_rate("XXX", rate)["rate_to_rub"] == expected


def test_full_weather_and_rate_summaries() -> None:
    assert pp.preprocess_weather(-3.2, "clear sky") == {
        "temp_c": -3.2,
        "description": "clear sky",
        "warm_clothes": True,
    }
    assert pp.preprocess_rate("usd", 92.15) == {
        "currency": "USD",
        "rate_to_rub": 92.15,
        "expensive": False,
    }
