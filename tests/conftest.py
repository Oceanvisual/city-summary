from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pytest
import structlog

from clients.cache import CACHE_DIR_ENV


@pytest.fixture(autouse=True)
def reset_structlog() -> Iterator[None]:
    """main() настраивает structlog глобально на sys.stderr, который capsys потом закрывает."""
    yield
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


@pytest.fixture(autouse=True)
def isolated_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Тесты никогда не пишут в настоящий ~/.cache."""
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv(CACHE_DIR_ENV, str(cache_dir))
    return cache_dir


@pytest.fixture
def sleep_mock() -> Iterator[mock.MagicMock]:
    with mock.patch("clients.http.time.sleep") as sleep:
        yield sleep


@pytest.fixture
def session_get() -> Iterator[mock.MagicMock]:
    with mock.patch("clients.http._session") as session:
        yield session.get
