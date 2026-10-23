"""Проверка формата и обязательных полей JSON внешних API через Pydantic."""

from pydantic import BaseModel, ConfigDict, ValidationError

from clients.exceptions import InvalidResponseError


class ResponseModel(BaseModel):
    """База схем ответов: строгие типы без NaN/inf, лишние поля игнорируются."""

    model_config = ConfigDict(strict=True, allow_inf_nan=False, extra="ignore", frozen=True)


def validate_payload[M: BaseModel](model: type[M], payload: object, *, source: str) -> M:
    """Валидирует JSON по схеме и переводит ошибки Pydantic в InvalidResponseError."""
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(map(str, error['loc'])) or '<root>'}: {error['msg']}"
            for error in exc.errors()[:3]
        )
        raise InvalidResponseError(f"{source}: неожиданный формат ответа ({details})") from exc
