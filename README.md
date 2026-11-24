# exception_local_variable_collector

A small library that captures the local variables from each frame in a raised exception's traceback into a structured, size-bounded dictionary.

```python
from exception_local_variable_collector import collect_locals

try:
    risky()
except Exception as exc:
    snapshot = collect_locals(exc, max_repr_len=120, max_total_len=4096)
    for frame in snapshot["frames"]:
        print(frame["filename"], frame["lineno"], frame["name"])
        for name, value in frame["locals"].items():
            print("   ", name, "=", value)
```

## Why this exists

When an exception is logged, the traceback tells you *where* it happened but not *what state* the program was in.  Attaching `frame.f_locals` to a log line is the obvious fix, but it has two problems: the values may be huge, and holding live references to them keeps the whole frame graph alive.  This library walks the traceback once, converts each local to a `repr()` string, and trims the result so it can be safely written to a log or error report.  The trade-off is that the captured values are strings, not objects -- you cannot re-use them as data, only read them.

## API

The package exports two names:

- `collect_locals(exc, max_repr_len=200, max_total_len=8192, max_vars_per_frame=50, include=None, exclude=None)` -- convenience function.
- `Collector(max_repr_len=200, max_total_len=8192, max_vars_per_frame=50, include=None, exclude=None)` -- reusable collector with a `.capture(exc)` method.

Both return a dictionary with a `"frames"` key containing a list of records.  Each record has `filename`, `lineno`, `name`, and `locals` (a mapping of variable name to repr string).  If any value was truncated or dropped, the top-level dictionary also has `"truncated": True`.

Limits may be set to `None` to disable them.  Negative limits raise `ValueError`.

## The awkward edge

The collector cannot guarantee that `repr()` will succeed.  A value with a broken `__repr__` is recorded as `"<unrepresentable>"` rather than aborting the capture.  Similarly, `max_total_len` is enforced with a fixed per-variable overhead estimate, so the serialized payload is bounded but not byte-exact against any particular JSON encoder.

## Design notes

The window stores values eagerly rather than keeping running aggregates. Running
sums drift with floating point over long streams, and recomputing from a small
buffer is cheap enough that the drift is not worth the speed.

