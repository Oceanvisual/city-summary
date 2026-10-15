"""CLI «Сводка по городу»: погода и курс валюты к рублю.

Коды выхода: 0 — успех, 2 — ошибка аргументов, 3 — город или код валюты не найден,
4 — внешний сервис недоступен после retry или ответил некорректно.
"""

import argparse
import json
import sys
import uuid
from collections.abc import Sequence
from enum import IntEnum

import structlog

from clients.exceptions import AppError, ExternalServiceError, NotFoundError
from clients.rates import default_rate_cache
from logging_config import configure_logging
from processing.service import CitySummary, build_city_summary

log = structlog.get_logger(__name__)


class ExitCode(IntEnum):
    OK = 0
    USAGE = 2  # argparse завершает процесс с этим кодом сам
    NOT_FOUND = 3
    SERVICE_UNAVAILABLE = 4
    INTERRUPTED = 130


def _city(value: str) -> str:
    city = value.strip()
    if not city:
        raise argparse.ArgumentTypeError("название города не может быть пустым")
    return city


def _currency(value: str) -> str:
    code = value.strip().upper()
    if len(code) != 3 or not code.isascii() or not code.isalpha():
        raise argparse.ArgumentTypeError(
            f"ожидается ISO-код валюты из трёх латинских букв, получено {value!r}"
        )
    return code


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Сводка по городу: текущая погода и курс валюты к рублю.",
    )
    parser.add_argument("--city", required=True, type=_city, help="город, например Moscow")
    parser.add_argument(
        "--currency",
        default="USD",
        type=_currency,
        help="ISO-код валюты, курс которой к рублю показать (по умолчанию USD)",
    )
    parser.add_argument("--json", action="store_true", help="вывести сводку в формате JSON")
    parser.add_argument(
        "--no-cache", action="store_true", help="не использовать кэш курса (TTL 5 минут)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="подробные логи в stderr")
    return parser.parse_args(argv)


def format_summary(summary: CitySummary) -> str:
    weather, rates = summary["weather"], summary["rates"]
    return "\n".join(
        [
            f"Город: {summary['city']}",
            f"Погода: {weather['temp_c']:.1f}°C, {weather['description']}",
            f"Тёплая одежда: {_yes_no(weather['warm_clothes'])}",
            f"{rates['currency']}→RUB: {rates['rate_to_rub']}",
            f"Дорогой курс: {_yes_no(rates['expensive'])}",
        ]
    )


def _yes_no(flag: bool) -> str:
    return "да" if flag else "нет"


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose)
    run_id = uuid.uuid4().hex[:8]
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(run_id=run_id)
    log.info("run_started", city=args.city, currency=args.currency, cache=not args.no_cache)

    try:
        summary = build_city_summary(
            args.city,
            args.currency,
            rate_cache=None if args.no_cache else default_rate_cache(),
        )
    except NotFoundError as exc:
        return _fail(exc, ExitCode.NOT_FOUND, run_id)
    except ExternalServiceError as exc:
        return _fail(exc, ExitCode.SERVICE_UNAVAILABLE, run_id)
    except KeyboardInterrupt:
        return ExitCode.INTERRUPTED

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(format_summary(summary))
    log.info("run_finished", exit_code=int(ExitCode.OK))
    return ExitCode.OK


def _fail(exc: AppError, code: ExitCode, run_id: str) -> ExitCode:
    log.info("run_failed", error_type=type(exc).__name__, exit_code=int(code))
    print(f"Ошибка: {exc} (run_id={run_id})", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
