from unittest import mock

import pytest
import requests

from clients import http
from clients.exceptions import InvalidResponseError, ServiceUnavailableError, UpstreamHTTPError
from tests.helpers import make_response

URL = "https://api.example.test/resource"


def test_returns_parsed_json_with_timeout(session_get: mock.MagicMock) -> None:
    session_get.return_value = make_response(200, {"ok": True})

    assert http.get_json(URL, params={"q": "x"}) == {"ok": True}

    session_get.assert_called_once_with(URL, params={"q": "x"}, timeout=http.TIMEOUT_SECONDS)
    assert 0 < http.TIMEOUT_SECONDS <= 10


@pytest.mark.parametrize(
    "error",
    [requests.exceptions.Timeout(), requests.exceptions.ConnectionError()],
    ids=["timeout", "connection_error"],
)
def test_retries_network_errors_with_backoff(
    session_get: mock.MagicMock, sleep_mock: mock.MagicMock, error: Exception
) -> None:
    session_get.side_effect = [error, error, make_response(200, {"ok": True})]

    assert http.get_json(URL) == {"ok": True}

    assert session_get.call_count == 3
    assert sleep_mock.call_args_list == [mock.call(0.5), mock.call(1.0)]


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_retries_transient_5xx(
    session_get: mock.MagicMock, sleep_mock: mock.MagicMock, status: int
) -> None:
    session_get.side_effect = [make_response(status), make_response(200, [1, 2])]

    assert http.get_json(URL) == [1, 2]
    assert session_get.call_count == 2


def test_gives_up_after_two_retries(
    session_get: mock.MagicMock, sleep_mock: mock.MagicMock
) -> None:
    session_get.side_effect = requests.exceptions.Timeout()

    with pytest.raises(ServiceUnavailableError, match="после 3 попыток") as exc_info:
        http.get_json(URL)

    assert session_get.call_count == 1 + http.MAX_RETRIES
    assert sleep_mock.call_count == http.MAX_RETRIES  # после последней попытки не спим
    assert isinstance(exc_info.value.__cause__, requests.exceptions.Timeout)


def test_429_waits_numeric_retry_after(
    session_get: mock.MagicMock, sleep_mock: mock.MagicMock
) -> None:
    session_get.side_effect = [
        make_response(429, headers={"Retry-After": "3"}),
        make_response(200, {"ok": True}),
    ]

    assert http.get_json(URL) == {"ok": True}
    sleep_mock.assert_called_once_with(3.0)


def test_429_with_http_date_falls_back_to_backoff(
    session_get: mock.MagicMock, sleep_mock: mock.MagicMock
) -> None:
    session_get.side_effect = [
        make_response(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}),
        make_response(200, {"ok": True}),
    ]

    assert http.get_json(URL) == {"ok": True}
    sleep_mock.assert_called_once_with(http.BACKOFF_BASE_SECONDS)


def test_429_with_too_long_retry_after_fails_fast(
    session_get: mock.MagicMock, sleep_mock: mock.MagicMock
) -> None:
    session_get.return_value = make_response(429, headers={"Retry-After": "3600"})

    with pytest.raises(ServiceUnavailableError, match="Retry-After=3600"):
        http.get_json(URL)

    session_get.assert_called_once()
    sleep_mock.assert_not_called()


@pytest.mark.parametrize("status", [400, 404, 422])
def test_client_errors_are_not_retried(
    session_get: mock.MagicMock, sleep_mock: mock.MagicMock, status: int
) -> None:
    session_get.return_value = make_response(status, {"message": "nope"})

    with pytest.raises(UpstreamHTTPError) as exc_info:
        http.get_json(URL)

    assert exc_info.value.status_code == status
    session_get.assert_called_once()
    sleep_mock.assert_not_called()


def test_non_json_body_is_invalid_response(session_get: mock.MagicMock) -> None:
    session_get.return_value = make_response(200, body=b"<html>maintenance</html>")

    with pytest.raises(InvalidResponseError, match="не JSON"):
        http.get_json(URL)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5", 5.0),
        ("0", 0.0),
        ("1.5", 1.5),
        (None, None),
        ("", None),
        ("soon", None),
        ("-1", None),
        ("nan", None),
        ("inf", None),
    ],
)
def test_parse_retry_after(value: str | None, expected: float | None) -> None:
    assert http.parse_retry_after(value) == expected
