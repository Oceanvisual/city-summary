"""Файловый TTL-кэш чисел.

CLI живёт доли секунды, поэтому кэш в памяти процесса бесполезен — храним JSON на диске.
Любая ошибка кэша только логируется: из-за кэша запрос падать не должен.
"""

import contextlib
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final

import structlog
from pydantic import BaseModel, TypeAdapter, ValidationError

log = structlog.get_logger(__name__)

CACHE_DIR_ENV: Final = "CITY_SUMMARY_CACHE_DIR"


class _Entry(BaseModel):
    value: float
    stored_at: float


_CacheData = TypeAdapter(dict[str, _Entry])


def default_cache_dir() -> Path:
    """$CITY_SUMMARY_CACHE_DIR, иначе $XDG_CACHE_HOME/city_summary, иначе ~/.cache/city_summary."""
    if custom := os.environ.get(CACHE_DIR_ENV):
        return Path(custom)
    xdg = os.environ.get("XDG_CACHE_HOME")
    return (Path(xdg) if xdg else Path.home() / ".cache") / "city_summary"


class FileTTLCache:
    def __init__(
        self,
        path: Path,
        ttl_seconds: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = path
        self._ttl = ttl_seconds
        self._clock = clock

    def get(self, key: str) -> float | None:
        entry = self._load().get(key)
        if entry is None:
            return None
        age = self._clock() - entry.stored_at
        if not 0 <= age < self._ttl:
            return None
        return entry.value

    def set(self, key: str, value: float) -> None:
        data = self._load()
        data[key] = _Entry(value=value, stored_at=self._clock())
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(_CacheData.dump_json(data))
            tmp.replace(self.path)  # атомарная замена: читатель не увидит полузаписанный файл
        except OSError as exc:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            log.warning("cache_write_failed", path=str(self.path), error=str(exc))

    def _load(self) -> dict[str, _Entry]:
        try:
            return _CacheData.validate_json(self.path.read_bytes())
        except FileNotFoundError:
            return {}
        except (OSError, ValidationError) as exc:
            log.warning("cache_read_failed", path=str(self.path), error=str(exc))
            return {}
