import json
from collections.abc import Iterator
from unittest import mock

import pytest

import main
from clients.cache import FileTTLCache
from clients.exceptions import (
    AppError,
    CityNotFoundError,
    CurrencyNotFoundError,
    InvalidResponseError,
    ServiceUnavailableError,
    UpstreamHTTPError,
)
from processing.service import CitySummary

SUMMARY: CitySummary = {
    "city": "Moscow",
    "weather": {"temp_c": -3.2, "description": "clear sky", "warm_clothes": True},
    "rates": {"currency": "USD", "rate_to_rub": 92.15, "expensive": False},
}


@pytest.fixture
def build() -> Iterator[mock.MagicMock]:
    with mock.patch("main.build_city_summary", return_value=SUMMARY) as patched:
        yield patched


def test_prints_text_summary(build: mock.MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    assert main.main(["--city", "Moscow"]) == 0

    assert capsys.readouterr().out == (
        "Город: Moscow\n"
        "Погода: -3.2°C, clear sky\n"
        "Тёплая одежда: да\n"
        "USD→RUB: 92.15\n"
        "Дорогой курс: нет\n"
    )
    args, kwargs = build.call_args
    assert args == ("Moscow", "USD")
    assert isinstance(kwargs["rate_cache"], FileTTLCache)


def test_json_output(build: mock.MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    assert main.main(["--city", "Moscow", "--json"]) == 0

    assert json.loads(capsys.readouterr().out) == SUMMARY


def test_currency_is_normalized_and_cache_can_be_disabled(build: mock.MagicMock) -> None:
    main.main(["--city", " Moscow ", "--currency", "eur", "--no-cache"])

    build.assert_called_once_with("Moscow", "EUR", rate_cache=None)


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--city", ""],
        ["--city", "   "],
        ["--city", "Moscow", "--currency", "US"],
        ["--city", "Moscow", "--currency", "US1"],
        ["--city", "Moscow", "--currency", "ДОЛ"],
        ["--city", "Moscow", "--unknown"],
    ],
)
def test_bad_arguments_exit_with_2(build: mock.MagicMock, argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main.main(argv)

    assert exc_info.value.code == 2
    build.assert_not_called()


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (CityNotFoundError("Atlantis"), 3),
        (CurrencyNotFoundError("XYZ"), 3),
        (ServiceUnavailableError("down"), 4),
        (InvalidResponseError("garbage"), 4),
        (UpstreamHTTPError("url", 400, ""), 4),
    ],
)
def test_errors_map_to_exit_codes(
    build: mock.MagicMock, capsys: pytest.CaptureFixture[str], error: AppError, code: int
) -> None:
    build.side_effect = error

    assert main.main(["--city", "Atlantis"]) == code

    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"Ошибка: {error}" in captured.err
    assert "run_id=" in captured.err


def test_verbose_logs_go_to_stderr_with_run_id(
    build: mock.MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    main.main(["--city", "Moscow", "-v"])

    captured = capsys.readouterr()
    assert "run_started" in captured.err
    assert "run_id=" in captured.err
    assert "run_started" not in captured.out
