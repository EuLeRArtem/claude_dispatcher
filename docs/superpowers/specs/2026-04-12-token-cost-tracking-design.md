# Token Cost Tracking — Design Spec

## Goal

Эмпирически измерять стоимость токенов в % utilization от лимитов Max-подписки. Копить данные по каждой сессии, визуализировать удельную стоимость на графике, алертить при аномально высокой стоимости.

## Background

Лимиты Anthropic Max — два скользящих окна (5h, 7d) с unified utilization 0.0–1.0. Разные модели и типы токенов имеют разный вес. Точные коэффициенты не публичны, но измеримы эмпирически: замерить utilization до и после сессии, сопоставить с token usage из транскрипта.

### Источники данных

- **Utilization**: headers из `/v1/messages` (`anthropic-ratelimit-unified-{5h,7d}-utilization`). Уже поллится в `limit_tracker.py`.
- **Token usage**: JSONL-транскрипт сессии Claude Code. Каждое `assistant` сообщение содержит `message.usage` с полями: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `model`.
- **Transcript path**: приходит в Stop hook payload как `transcript_path`.

## Data Flow

```
1. session_manager.start_*()
   → limit_tracker.poll_once() → snapshot (5h_util, 7d_util)
   → сохранить в SessionInfo.util_snapshot

2. Сессия работает, транскрипт пишется в JSONL...

3. hook_server получает Stop hook
   → transcript_path из payload
   → transcript_parser.parse(transcript_path) → SessionUsage
   → limit_tracker.poll_once() → snapshot "после"
   → delta = after - before
   → cost_tracker.record(SessionCost{...})
   → (тихо, без уведомления — просто запись в CSV)
```

## New Components

### `core/transcript_parser.py`

```python
@dataclass
class SessionUsage:
    model: str                        # "claude-opus-4-6" (основная модель сессии)
    input_tokens: int                 # сумма по всем assistant messages
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    request_count: int                # количество assistant messages

def parse_transcript(path: str) -> SessionUsage | None
```

- Читает JSONL построчно (`encoding='utf-8'`)
- Фильтрует `type == "assistant"` с `message.usage`
- Модель: берёт из `message.model`, считает самую частую (mode) — это основная модель сессии
- Возвращает `None` если файл не найден или нет assistant messages

### `core/cost_tracker.py`

```python
@dataclass
class SessionCost:
    timestamp: str                    # ISO, момент Stop hook
    session_id: str
    project: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    request_count: int
    util_before_5h: float
    util_after_5h: float
    util_before_7d: float
    util_after_7d: float
    delta_5h: float                   # after - before (может быть отрицательной — decay)
    delta_7d: float
    concurrent: bool                  # были ли другие активные сессии
    duration_min: int                 # длительность сессии

class CostTracker:
    def __init__(self, data_dir: str = "data/costs")
    def record(self, cost: SessionCost) -> None        # append to CSV
    def load(self, year_month: str) -> list[dict]      # read CSV
```

**CSV**: `data/costs/YYYY-MM.csv`, формат аналогичен `data/usage/`.

## Changes to Existing Modules

### `core/limit_tracker.py`

- `_poll_once()` → `poll_once()` (публичный)
- Без других изменений — метод уже возвращает `UsageData | None`

### `core/session_manager.py`

- `SessionInfo` получает новое поле: `util_snapshot: UsageData | None = None`
- При старте сессии (`start_remote()`, `start_normal()`):
  - Вызвать `limit_tracker.poll_once()` → сохранить в `info.util_snapshot`
  - Если poll вернул `None` — стартуем без snapshot (не блокируем запуск)

### `core/hook_server.py`

- При Stop event:
  - Прочитать `transcript_path` из payload
  - Вызвать `transcript_parser.parse(transcript_path)` → `SessionUsage`
  - Вызвать `limit_tracker.poll_once()` → utilization "после"
  - Найти сессию по `cwd` → взять `util_snapshot` (utilization "до")
  - Определить `concurrent` = `len(session_manager.list_sessions()) > 1`
  - Собрать `SessionCost`, вызвать `cost_tracker.record()`
  - Если `transcript_path` отсутствует или парсинг не удался — записать только utilization delta без token breakdown
- HookServer.__init__ получает `cost_tracker` и `limit_tracker` как зависимости

### `analytics/charts.py`

Новый метод `generate_token_cost(date_str: str) -> str | None`:

- Читает `data/costs/YYYY-MM.csv`
- Показывает последние 7 дней (аналогично `generate_week`)
- Ось X: время
- Ось Y: удельная стоимость = `delta_5h / output_tokens * 1000` (% за 1K output tokens)
- Точки: по одной на сессию
- Цвет/маркер: по модели (Opus, Sonnet, Haiku)
- Помечает concurrent-сессии другим стилем (полупрозрачные)

### `analytics/handlers.py`

- Новая кнопка "💰 Стоимость" в клавиатуре графиков (рядом с "День", "Неделя", "Heatmap")
- `CB_CHART_COST = "chart_cost"`
- Хендлер `chart_cost` → вызывает `charts.generate_token_cost(today)`

### `core/notifier.py`

Новый метод `cost_warning()` — алерт при аномально высокой стоимости токена. Порог определим позже, когда накопим данные. В первой версии метод создаём, но не вызываем — только заготовка.

## Edge Cases

| Ситуация | Поведение |
|---|---|
| Параллельные сессии | `concurrent=true`, дельта включает расход обеих |
| Snapshot "до" не удался (401/429) | Стартуем без snapshot, `util_before_*` = null, дельта не считается |
| `transcript_path` нет в payload | Записываем только utilization delta без token breakdown |
| Файл транскрипта не найден | Warning в лог, записываем только utilization delta |
| IDE-сессия (process=None) | Работает идентично — Stop hook приходит, transcript_path есть |
| Отрицательная дельта | Возможна из-за decay скользящего окна — записываем as-is |

## Storage

```
data/
├── costs/
│   └── YYYY-MM.csv       — одна строка на сессию (SessionCost fields)
├── usage/                 — существующий (без изменений)
└── charts/                — существующий
```

## NOT in scope

- Предикторы ("лимит кончится через X часов")
- Бюджет на сессию перед запуском
- Per-turn трекинг (внутри сессии)
- Фиксированный порог алерта (определим после накопления данных)
