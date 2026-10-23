"""Общий GET для внешних API: timeout, retry с backoff, учёт Retry-After, разбор JSON."""

import math
import time
from collections.abc import Mapping
from typing import Final

import requests
import structlog

from clients.exceptions import InvalidResponseError, ServiceUnavailableError, UpstreamHTTPError

log = structlog.get_logger(__name__)

TIMEOUT_SECONDS: Final = 5.0
"""Timeout и на соединение, и на чтение каждого запроса (требование — не больше 10 с)."""

MAX_RETRIES: Final = 2
"""Сколько повторов делать после первой попытки."""

BACKOFF_BASE_SECONDS: Final = 0.5
"""Экспоненциальная пауза между попытками: 0.5 с, 1 с, ..."""

MAX_RETRY_AFTER_SECONDS: Final = 10.0
"""Если сервис просит подождать дольше, сдаёмся сразу: CLI, висящий минуту, хуже кода 4."""

RETRYABLE_STATUSES: Final = frozenset({500, 502, 503, 504})
TOO_MANY_REQUESTS: Final = 429
RETRYABLE_EXCEPTIONS: Final = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
)

type QueryParams = Mapping[str, str | int | float]

_session = requests.Session()
_session.headers["User-Agent"] = "city-summary/0.1"


def get_json(url: str, params: QueryParams | None = None) -> object:
    """Выполняет GET с retry и возвращает разобранный, но ещё не провалидированный JSON.

    Повторяет запрос при Timeout, ConnectionError и HTTP 500/502/503/504 с экспоненциальной
    паузой; при HTTP 429 ждёт столько, сколько указано в числовом Retry-After.

    Raises:
        ServiceUnavailableError: запрос не удался после всех повторов.
        UpstreamHTTPError: неретраимый статус ошибки (4xx, кроме 429).
        InvalidResponseError: тело успешного ответа — не JSON.
    """
    attempts = MAX_RETRIES + 1
    failure = ""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        delay = BACKOFF_BASE_SECONDS * 2 ** (attempt - 1)
        log.debug("http_request", url=url, params=params, attempt=attempt)
        try:
            response = _session.get(url, params=params, timeout=TIMEOUT_SECONDS)
        except RETRYABLE_EXCEPTIONS as exc:
            failure, last_error = type(exc).__name__, exc
        else:
            status = response.status_code
            log.debug(
                "http_response",
                url=url,
                status=status,
                elapsed_ms=round(response.elapsed.total_seconds() * 1000),
            )
            if status == TOO_MANY_REQUESTS:
                failure = "HTTP 429"
                retry_after = parse_retry_after(response.headers.get("Retry-After"))
                if retry_after is not None:
                    if retry_after > MAX_RETRY_AFTER_SECONDS:
                        raise ServiceUnavailableError(
                            f"{url}: превышен лимит запросов, Retry-After={retry_after:g} с"
                        )
                    delay = retry_after
            elif status in RETRYABLE_STATUSES:
                failure = f"HTTP {status}"
            elif status >= 400:
                raise UpstreamHTTPError(url, status, response.text)
            else:
                return _decode_json(response)

        if attempt < attempts:
            log.warning("http_retry", url=url, attempt=attempt, reason=failure, delay_s=delay)
            time.sleep(delay)

    raise ServiceUnavailableError(
        f"{url}: сервис недоступен после {attempts} попыток (последняя ошибка: {failure})"
    ) from last_error


def parse_retry_after(value: str | None) -> float | None:
    """Числовой Retry-After в секундах. HTTP-date и мусор → None (тогда работает backoff)."""
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return seconds


def _decode_json(response: requests.Response) -> object:
    try:
        return response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise InvalidResponseError(f"{response.url}: тело ответа — не JSON") from exc
