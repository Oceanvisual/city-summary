"""Исключения приложения, в которые клиенты переводят ошибки внешних сервисов.

Иерархия повторяет коды выхода CLI:
- NotFoundError        → 3 (город или валюта не найдены);
- ExternalServiceError → 4 (сервис недоступен или ответил не так, как ожидалось).
"""


class AppError(Exception):
    """Базовая ошибка приложения."""


class NotFoundError(AppError):
    """Внешний сервис не знает запрошенную сущность."""


class CityNotFoundError(NotFoundError):
    def __init__(self, city: str) -> None:
        super().__init__(f"город не найден: {city!r}")
        self.city = city


class CurrencyNotFoundError(NotFoundError):
    def __init__(self, currency: str) -> None:
        super().__init__(f"код валюты не найден: {currency!r}")
        self.currency = currency


class ExternalServiceError(AppError):
    """Внешний сервис не дал пригодного ответа."""


class ServiceUnavailableError(ExternalServiceError):
    """Сеть, timeout, 5xx или 429 не прошли после всех повторов."""


class InvalidResponseError(ExternalServiceError):
    """Ответ не прошёл проверку формата или обязательных полей."""


class UpstreamHTTPError(ExternalServiceError):
    """Неретраимый HTTP-статус ошибки (4xx, кроме 429).

    Клиенты конкретных API решают, означает ли статус «не найдено».
    """

    def __init__(self, url: str, status_code: int, body: str) -> None:
        super().__init__(f"{url} ответил HTTP {status_code}")
        self.url = url
        self.status_code = status_code
        self.body = body[:500]
