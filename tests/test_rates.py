from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pytest

from clients import rates
from clients.cache import FileTTLCache
from clients.exceptions import (
    CurrencyNotFoundError,
    InvalidResponseError,
    ServiceUnavailableError,
    UpstreamHTTPError,
)

USD_OK = {"date": "2026-10-15", "base": "USD", "quote": "RUB", "rate": 83.92}


@pytest.fixture
def get_json() -> Iterator[mock.MagicMock]:
    with mock.patch("clients.rates.get_json") as patched:
        yield patched


class FakeClock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_returns_rate_and_normalizes_code(get_json: mock.MagicMock) -> None:
    get_json.return_value = USD_OK

    assert rates.get_rate(" usd ") == 83.92
    get_json.assert_called_once_with("https://api.frankfurter.dev/v2/rate/USD/RUB")


@pytest.mark.parametrize("status", [404, 422])
def test_unknown_currency_raises_not_found(get_json: mock.MagicMock, status: int) -> None:
    get_json.side_effect = UpstreamHTTPError("url", status, '{"message":"invalid currency"}')

    with pytest.raises(CurrencyNotFoundError, match="XYZ"):
        rates.get_rate("XYZ")


def test_other_http_errors_propagate(get_json: mock.MagicMock) -> None:
    get_json.side_effect = UpstreamHTTPError("url", 400, "bad request")

    with pytest.raises(UpstreamHTTPError):
        rates.get_rate("USD")


def test_unavailable_service_propagates(get_json: mock.MagicMock) -> None:
    get_json.side_effect = ServiceUnavailableError("down")

    with pytest.raises(ServiceUnavailableError):
        rates.get_rate("USD")


@pytest.mark.parametrize(
    "payload",
    [
        {"base": "USD", "quote": "RUB"},
        {"base": "USD", "quote": "RUB", "rate": "83.92"},
        {"base": "USD", "quote": "RUB", "rate": 0},
        {"base": "USD", "quote": "RUB", "rate": -1.5},
        {"rates": {"RUB": 83.92}},
        None,
    ],
    ids=["no_rate", "rate_as_string", "zero_rate", "negative_rate", "v1_format", "null"],
)
def test_malformed_payload_is_invalid_response(get_json: mock.MagicMock, payload: object) -> None:
    get_json.return_value = payload

    with pytest.raises(InvalidResponseError, match="Frankfurter"):
        rates.get_rate("USD")


def test_mismatched_currency_pair_is_invalid_response(get_json: mock.MagicMock) -> None:
    get_json.return_value = {**USD_OK, "base": "EUR"}

    with pytest.raises(InvalidResponseError, match="получен EUR→RUB"):
        rates.get_rate("USD")


def test_cache_hit_skips_http(get_json: mock.MagicMock, tmp_path: Path) -> None:
    cache = FileTTLCache(tmp_path / "rates.json", ttl_seconds=rates.RATE_CACHE_TTL_SECONDS)
    get_json.return_value = USD_OK

    assert rates.get_rate("USD", cache=cache) == 83.92
    assert rates.get_rate("usd", cache=cache) == 83.92

    get_json.assert_called_once()


def test_cache_expires_after_five_minutes(get_json: mock.MagicMock, tmp_path: Path) -> None:
    clock = FakeClock()
    cache = FileTTLCache(tmp_path / "rates.json", rates.RATE_CACHE_TTL_SECONDS, clock=clock)
    get_json.side_effect = [USD_OK, {**USD_OK, "rate": 85.0}]

    assert rates.get_rate("USD", cache=cache) == 83.92
    clock.now += 5 * 60 - 1
    assert rates.get_rate("USD", cache=cache) == 83.92
    clock.now += 1
    assert rates.get_rate("USD", cache=cache) == 85.0

    assert get_json.call_count == 2


def test_cache_is_per_currency(get_json: mock.MagicMock, tmp_path: Path) -> None:
    cache = FileTTLCache(tmp_path / "rates.json", rates.RATE_CACHE_TTL_SECONDS)
    get_json.side_effect = [USD_OK, {**USD_OK, "base": "EUR", "rate": 93.98}]

    assert rates.get_rate("USD", cache=cache) == 83.92
    assert rates.get_rate("EUR", cache=cache) == 93.98


def test_default_cache_respects_env(isolated_cache_dir: Path) -> None:
    assert rates.default_rate_cache().path == isolated_cache_dir / "rates.json"
