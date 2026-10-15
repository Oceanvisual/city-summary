from pathlib import Path

from clients.cache import FileTTLCache


def test_roundtrip_persists_between_instances(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "rates.json"
    FileTTLCache(path, ttl_seconds=60).set("USD/RUB", 83.92)

    assert FileTTLCache(path, ttl_seconds=60).get("USD/RUB") == 83.92
    assert FileTTLCache(path, ttl_seconds=60).get("EUR/RUB") is None


def test_entry_from_the_future_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "rates.json"
    FileTTLCache(path, 60, clock=lambda: 2_000.0).set("USD/RUB", 1.0)

    assert FileTTLCache(path, 60, clock=lambda: 1_000.0).get("USD/RUB") is None


def test_corrupted_file_is_treated_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "rates.json"
    path.write_text("{not json", encoding="utf-8")
    cache = FileTTLCache(path, ttl_seconds=60)

    assert cache.get("USD/RUB") is None
    cache.set("USD/RUB", 83.92)  # перезаписывает битый файл
    assert cache.get("USD/RUB") == 83.92


def test_wrong_schema_is_treated_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "rates.json"
    path.write_text('{"USD/RUB": 83.92}', encoding="utf-8")

    assert FileTTLCache(path, ttl_seconds=60).get("USD/RUB") is None


def test_unwritable_location_does_not_raise(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")
    cache = FileTTLCache(blocker / "rates.json", ttl_seconds=60)  # родитель — файл, не каталог

    cache.set("USD/RUB", 83.92)

    assert cache.get("USD/RUB") is None
    assert list(tmp_path.iterdir()) == [blocker]  # временный файл не остался
