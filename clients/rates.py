"""Клиент Frankfurter: курс валюты к рублю с файловым кэшем на 5 минут."""

from typing import Annotated, Final
from urllib.parse import quote

import structlog
from pydantic import Field

from clients.cache import FileTTLCache, default_cache_dir
from clients.exceptions import CurrencyNotFoundError, InvalidResponseError, UpstreamHTTPError
from clients.http import get_json
from clients.validation import ResponseModel, validate_payload

log = structlog.get_logger(__name__)

RATE_URL: Final = "https://api.frankfurter.dev/v2/rate/{currency}/{quote}"
QUOTE_CURRENCY: Final = "RUB"
RATE_CACHE_TTL_SECONDS: Final = 5 * 60

# Frankfurter отвечает 422 «invalid currency» на неизвестный код; 404 — на всякий случай.
NOT_FOUND_STATUSES: Final = frozenset({404, 422})


class _RateResponse(ResponseModel):
    base: str
    quote: str
    rate: Annotated[float, Field(gt=0)]


def default_rate_cache() -> FileTTLCache:
    return FileTTLCache(default_cache_dir() / "rates.json", ttl_seconds=RATE_CACHE_TTL_SECONDS)


def get_rate(currency: str, *, cache: FileTTLCache | None = None) -> float:
    """Сколько рублей стоит единица валюты.

    Raises:
        CurrencyNotFoundError: Frankfurter не знает такой код валюты.
        ServiceUnavailableError, InvalidResponseError, UpstreamHTTPError: проблемы Frankfurter.
    """
    code = currency.strip().upper()
    cache_key = f"{code}/{QUOTE_CURRENCY}"
    if cache is not None and (cached := cache.get(cache_key)) is not None:
        log.info("rate_cache_hit", currency=code, rate=cached)
        return cached

    url = RATE_URL.format(currency=quote(code, safe=""), quote=QUOTE_CURRENCY)
    try:
        payload = get_json(url)
    except UpstreamHTTPError as exc:
        if exc.status_code in NOT_FOUND_STATUSES:
            raise CurrencyNotFoundError(code) from exc
        raise

    data = validate_payload(_RateResponse, payload, source="Frankfurter")
    if (data.base, data.quote) != (code, QUOTE_CURRENCY):
        raise InvalidResponseError(
            f"Frankfurter: запрошен курс {code}→{QUOTE_CURRENCY}, получен {data.base}→{data.quote}"
        )

    log.info("rate_fetched", currency=code, rate=data.rate)
    if cache is not None:
        cache.set(cache_key, data.rate)
    return data.rate
