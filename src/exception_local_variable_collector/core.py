"""Core implementation of the exception local variable collector.

The collector walks the traceback of a raised exception and snapshots
``frame.f_locals`` for each frame.  Snapshots are bounded in two ways:

* ``max_repr_len`` truncates any single ``repr()`` result.
* ``max_total_len`` truncates the overall serialized payload.

We deliberately store ``repr()`` strings rather than live objects.  Live
references would keep the whole frame graph alive (a memory leak) and
would risk raising a second exception while formatting the first one.
The trade-off is that the captured values are not re-usable as objects;
they are diagnostic strings.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

__all__ = ["Collector", "collect_locals"]

# A sentinel object lets us distinguish "the caller did not pass a limit"
# from "the caller passed None", which is a meaningful value.
_UNSET = object()


class Collector:
    """Collect local variables from exception tracebacks.

    Parameters
    ----------
    max_repr_len:
        Maximum length of a single variable's ``repr()``.  Values longer
        than this are truncated and suffixed with ``"..."``.  ``None``
        disables per-value truncation.
    max_total_len:
        Maximum length of the total serialized payload.  When the running
        total would exceed this, the offending value is truncated so the
        payload fits exactly; once the budget is exhausted, no further
        values are added.  ``None`` disables total truncation.
    max_vars_per_frame:
        Maximum number of variables captured from a single frame.  Extra
        variables are dropped.  ``None`` disables the cap.
    include:
        Optional iterable of variable names to include.  When given, only
        those names are captured.  ``None`` captures every name.
    exclude:
        Optional iterable of variable names to exclude.  Applied after
        ``include``.
    """

    def __init__(
        self,
        max_repr_len: Optional[int] = 200,
        max_total_len: Optional[int] = 8192,
        max_vars_per_frame: Optional[int] = 50,
        include: Optional[Iterable[str]] = None,
        exclude: Optional[Iterable[str]] = None,
    ) -> None:
        if max_repr_len is not None and max_repr_len < 0:
            raise ValueError("max_repr_len must be non-negative or None")
        if max_total_len is not None and max_total_len < 0:
            raise ValueError("max_total_len must be non-negative or None")
        if max_vars_per_frame is not None and max_vars_per_frame < 0:
            raise ValueError("max_vars_per_frame must be non-negative or None")
        self.max_repr_len = max_repr_len
        self.max_total_len = max_total_len
        self.max_vars_per_frame = max_vars_per_frame
        self.include = set(include) if include is not None else None
        self.exclude = set(exclude) if exclude is not None else set()

    def capture(self, exc: BaseException) -> Dict[str, Any]:
        """Capture locals from every frame in ``exc``'s traceback.

        Returns a dictionary with a ``"frames"`` key mapping to a list of
        frame records.  Each record contains the frame's ``filename``,
        ``lineno``, ``name``, and a ``"locals"`` mapping of variable names
        to truncated repr strings.  A ``"truncated"`` key is set to ``True``
        when any value was truncated or omitted.
        """
        tb = exc.__traceback__
        frames: List[Dict[str, Any]] = []
        total = 0
        any_truncated = False

        while tb is not None:
            frame = tb.tb_frame
            frame_locals = self._capture_frame(frame)
            record = {
                "filename": frame.f_code.co_filename,
                "lineno": tb.tb_lineno,
                "name": frame.f_code.co_name,
                "locals": frame_locals,
            }
            frames.append(record)
            tb = tb.tb_next

        # Apply the global budget across all frames after per-frame capture.
        if self.max_total_len is not None:
            frames, any_truncated = self._apply_total_budget(frames)

        result: Dict[str, Any] = {"frames": frames}
        if any_truncated:
            result["truncated"] = True
        return result

    def _capture_frame(self, frame: Any) -> Dict[str, str]:
        """Capture a single frame's locals as repr strings."""
        result: Dict[str, str] = {}
        names = sorted(frame.f_locals.keys())
        if self.include is not None:
            names = [n for n in names if n in self.include]
        names = [n for n in names if n not in self.exclude]
        if self.max_vars_per_frame is not None:
            names = names[: self.max_vars_per_frame]

        for name in names:
            value = frame.f_locals[name]
            try:
                text = repr(value)
            except Exception:
                # A pathological __repr__ must not abort the whole capture.
                text = "<unrepresentable>"
            if self.max_repr_len is not None and len(text) > self.max_repr_len:
                text = text[: self.max_repr_len] + "..."
            result[name] = text
        return result

    def _apply_total_budget(
        self, frames: List[Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], bool]:
        """Trim the serialized payload to ``max_total_len`` characters.

        We measure the length of the JSON-ish representation by summing
        the lengths of the repr strings plus a small fixed overhead per
        variable and per frame.  This keeps the accounting deterministic
        and independent of the exact serializer used by the caller.
        """
        budget = self.max_total_len
        assert budget is not None
        used = 0
        truncated = False
        new_frames: List[Dict[str, Any]] = []

        for record in frames:
            new_locals: Dict[str, str] = {}
            for name, text in record["locals"].items():
                # Overhead: name + separators.  Exact JSON size is not the
                # contract; a stable, generous estimate is.
                overhead = len(name) + 4
                if used + overhead + len(text) > budget:
                    remaining = budget - used - overhead
                    if remaining > 0:
                        new_locals[name] = text[:remaining] + "..."
                        used += overhead + remaining + 3
                    truncated = True
                    break
                new_locals[name] = text
                used += overhead + len(text)
            new_record = dict(record)
            new_record["locals"] = new_locals
            new_frames.append(new_record)
            if used >= budget:
                truncated = True
                break

        return new_frames, truncated


def collect_locals(
    exc: BaseException,
    max_repr_len: Optional[int] = 200,
    max_total_len: Optional[int] = 8192,
    max_vars_per_frame: Optional[int] = 50,
    include: Optional[Iterable[str]] = None,
    exclude: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Capture locals from every frame in ``exc``'s traceback.

    Convenience wrapper around :class:`Collector`.  See the class for the
    meaning of each parameter.
    """
    return Collector(
        max_repr_len=max_repr_len,
        max_total_len=max_total_len,
        max_vars_per_frame=max_vars_per_frame,
        include=include,
        exclude=exclude,
    ).capture(exc)
