import json

import requests


def make_response(
    status: int = 200,
    payload: object = None,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    url: str = "https://api.example.test/resource",
) -> requests.Response:
    """Настоящий requests.Response: у него честные .ok, .json() и регистронезависимые заголовки."""
    response = requests.Response()
    response.status_code = status
    response.url = url
    response.encoding = "utf-8"
    response.headers.update(headers or {})
    response._content = body if body is not None else json.dumps(payload).encode()
    return response
