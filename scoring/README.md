# scoring/

Pure-Python implementation of the behavioral scoring algorithm described in
[`docs/scoring-design.md`](../docs/scoring-design.md). No I/O, no database,
no hardware dependency — give it events and a date, get a score.

| File | What it holds |
|---|---|
| `models.py` | Enums, dataclasses, and every tunable constant (weights, half-lives, windows, caps) |
| `engine.py` | The math: per-event weighting, decay, trust credit, driver score, company roll-up |

Every function docstring cites the design-doc section it implements.

## Try it

```python
from datetime import date
from scoring.models import Event, EventType, Ledger, Source
from scoring.engine import score_driver

events = [Event(date(2026, 9, 13), EventType.HOS, 2, Ledger.DRIVER, Source.ELD)]
result = score_driver(events, employment_start=date(2025, 9, 1), as_of=date(2026, 9, 13))
print(result.score, result.band)   # 900.0 Band.EXEMPLARY
```

## Tests

```
pip install pytest
python -m pytest tests/ -v
```

Each test is a row from a worked-example table in the design doc. If the
doc and the code disagree, a test fails — that's the point.
