# Token Usage Chart — Design Spec

## Summary

Add a cumulative input/output token chart with two subplots (day and week) to the Telegram bot analytics, accessible via a single button on the Limits screen.

## Chart Layout

Single image with two subplots (stacked vertically):

- **Top subplot** — cumulative input/output tokens for today (5h-scale view)
- **Bottom subplot** — cumulative input/output tokens for the last 7 days (7d-scale view)

Each subplot has two lines:
- Input tokens (blue)
- Output tokens (purple)

Y-axis auto-scales with human-readable labels (50K, 1.2M, etc).

## Data Source

`CostTracker` CSV files (`data/costs/YYYY-MM.csv`), fields used:
- `timestamp` — session completion time
- `input_tokens` — total input tokens for the session
- `output_tokens` — total output tokens for the session

Sessions are sorted by timestamp, then cumulative sums are computed for each token type.

## UI

New button `📊 Токены` added to:
1. The `show_limits` keyboard (row with `💰 Стоимость`)
2. The `_chart_kb` keyboard (same row)

Callback data: `chart_tokens`

## Architecture

### Modified: `analytics/charts.py`

New method `generate_tokens(date_str: str) -> str | None`:
- Loads cost data for relevant months (current + previous if week spans boundary)
- Filters rows for today (top subplot) and last 7 days (bottom subplot)
- Computes cumulative sums of `input_tokens` and `output_tokens`
- Renders `fig, (ax_day, ax_week) = plt.subplots(2, 1, figsize=(10, 8))`
- Saves to `data/charts/tokens_{date_str}.png`
- Returns path or None if no data

### Modified: `analytics/handlers.py`

- New `CB_CHART_TOKENS = "chart_tokens"` constant
- New `chart_tokens` handler (same pattern as `chart_day`, `chart_week`, etc.)
- Button added to `show_limits` keyboard and `_chart_kb`
- Registered as `CallbackQueryHandler` in return list

## Testing

- Unit test for `generate_tokens` with mock cost data (verify file created, no crash on empty data)
