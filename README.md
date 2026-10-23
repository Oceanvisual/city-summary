# City Summary — «Сводка по городу»

CLI-утилита: получает текущую погоду в городе и курс выбранной валюты к рублю из внешних API,
приводит ответы к единому виду, применяет правила предобработки и печатает сводку в stdout.

```text
$ python main.py --city Moscow
Город: Moscow
Погода: -3.2°C, clear sky
Тёплая одежда: да
USD→RUB: 92.15
Дорогой курс: нет
```

## Требования

- Python 3.12
- Доступ в интернет (ключи API не нужны)

## Установка

Вариант 1 — `venv` + `pip`:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Вариант 2 — [uv](https://docs.astral.sh/uv/) (сам поставит Python 3.12 и зависимости из `uv.lock`):

```bash
uv sync
source .venv/bin/activate
```

## Запуск

```bash
python main.py --city Moscow                  # курс USD→RUB (по умолчанию)
python main.py --city Moscow --currency EUR   # курс EUR→RUB
python main.py --city "Saint Petersburg" --json
python main.py --city Moscow -v               # подробные логи в stderr
```

| Аргумент | Описание |
|---|---|
| `--city` | Город (обязательный). Регистр не важен: `moscow` → `Moscow`. |
| `--currency` | ISO-код валюты из трёх латинских букв, по умолчанию `USD`. |
| `--json` | Вывести сводку в JSON вместо текста. |
| `--no-cache` | Не использовать кэш курса. |
| `-v`, `--verbose` | Логи уровня DEBUG в stderr (по умолчанию — только предупреждения). |

### Коды выхода

| Код | Когда |
|---|---|
| `0` | Успех |
| `2` | Ошибка аргументов (нет `--city`, пустой город, `--currency 12`, ...) |
| `3` | Город или код валюты не найден (`--city Qwzxq`, `--currency XYZ`) |
| `4` | Внешний сервис недоступен после повторов или вернул некорректный ответ |

Сообщение об ошибке пишется в stderr вместе с `run_id` для поиска по логам.

### JSON-вывод

```json
{
  "city": "Moscow",
  "weather": {"temp_c": -3.2, "description": "clear sky", "warm_clothes": true},
  "rates": {"currency": "USD", "rate_to_rub": 92.15, "expensive": false}
}
```

## Внешние API

| Данные | API | Запросы |
|---|---|---|
| Погода | [Open-Meteo](https://open-meteo.com/en/docs) | `GET geocoding-api.open-meteo.com/v1/search` → координаты, затем `GET api.open-meteo.com/v1/forecast?current=temperature_2m,weather_code` |
| Курс | [Frankfurter](https://frankfurter.dev) | `GET api.frankfurter.dev/v2/rate/{currency}/RUB` |

Open-Meteo отдаёт погоду кодом WMO — клиент переводит его в текст (`0` → `clear sky`).

## Архитектура

```text
city-summary/
├── main.py                  # CLI: argparse, вызов build_city_summary, вывод, коды выхода
├── logging_config.py        # structlog → stderr, run_id в каждой записи
├── clients/                 # только общение с внешними API
│   ├── http.py              # общий GET: timeout, retry, Retry-After, разбор JSON
│   ├── validation.py        # Pydantic-схемы ответов → InvalidResponseError
│   ├── exceptions.py        # исключения приложения (NotFound → 3, ExternalService → 4)
│   ├── cache.py             # файловый TTL-кэш
│   ├── weather.py           # get_weather(city) → dict
│   └── rates.py             # get_rate(currency) → float, кэш на 5 минут
├── processing/
│   ├── preprocessing.py     # правила: warm_clothes, expensive, описание по умолчанию, округление
│   └── service.py           # build_city_summary(city, currency="USD") → dict
└── tests/                   # pytest + unittest.mock, сеть не трогают
```

- `clients/` не печатает в консоль и не знает про CLI — только HTTP, валидация и перевод ошибок
  внешних сервисов в исключения приложения.
- `processing/` не делает HTTP-запросов сам — получает данные от клиентов и применяет правила.
- `main.py` переводит исключения в коды выхода и печатает результат.

## Надёжность HTTP

- Только `GET`, timeout **5 с** на соединение и чтение каждого запроса.
- **2 повтора** после первой попытки (всего 3) при `requests.exceptions.Timeout`,
  `requests.exceptions.ConnectionError` и HTTP 500/502/503/504; пауза 0.5 с → 1 с.
- HTTP 429: ждём столько, сколько сказано в числовом `Retry-After`. Если он больше 10 с — сразу
  код 4, а не зависание. Если заголовка нет или он в формате даты — обычная пауза.
- Прочие 4xx не повторяются. Frankfurter на неизвестный код валюты отвечает 422 → код выхода 3.
- Ответ проверяется Pydantic-схемой в strict-режиме: статус, что тело — JSON, обязательные поля и
  их типы (`"rate": "83.9"` строкой — ошибка), диапазоны (курс > 0, широта ±90), отсутствие
  NaN/inf, совпадение валютной пары. Любое несоответствие → понятная `InvalidResponseError`.

## Правила предобработки

Все правила — в `processing/preprocessing.py` и зависят от полученных данных:

| Правило | Условие |
|---|---|
| `warm_clothes` | температура < 0 °C |
| `expensive` | курс > 100 ₽ |
| Описание погоды по умолчанию | пустое описание (неизвестный код WMO) → `нет данных` |
| Точность курса | курс ≥ 1 — до копеек, меньше 1 (KZT, JPY) — 4 значащие цифры |

Флаги считаются по округлённым значениям, чтобы вывод был согласован: `-0.04 °C` выводится как
`0.0°C`, и тёплая одежда при этом не нужна.

## Дополнительно

- **Логи с `run_id`** — structlog, каждая запись запуска помечена коротким `run_id`; логи идут в
  stderr, stdout остаётся чистым для сводки и `--json`.
- **Кэш курса на 5 минут** — файл `~/.cache/city_summary/rates.json` (переопределяется через
  `CITY_SUMMARY_CACHE_DIR` или `XDG_CACHE_HOME`). Кэш в памяти бесполезен — процесс CLI живёт доли
  секунды. Ошибки чтения или записи кэша не ломают запрос.
- **Тесты клиентов через `unittest.mock`** — retry, Retry-After, валидация, коды выхода, кэш.
- **Типизация** — `mypy --strict`, Pydantic для внешних данных, TypedDict для сводки.
- **Флаг `--json`**.
- **CI** — GitHub Actions: ruff, mypy, pytest, синхронность `requirements*.txt` с `uv.lock`.

## Разработка

```bash
uv sync                    # или: pip install -r requirements-dev.txt
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

Зависимости описаны в `pyproject.toml` и зафиксированы в `uv.lock`; `requirements*.txt`
генерируются из lock-файла:

```bash
uv export --format requirements-txt --no-hashes --no-dev -o requirements.txt
uv export --format requirements-txt --no-hashes -o requirements-dev.txt
```
