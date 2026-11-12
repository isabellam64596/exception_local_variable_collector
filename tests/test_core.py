import unittest

from exception_local_variable_collector import Collector, collect_locals


def _make_exception():
    outer = 1

    def inner():
        alpha = "a"
        beta = [1, 2, 3]
        raise ValueError("boom")

    try:
        inner()
    except ValueError as exc:
        return exc


class TestCollectLocals(unittest.TestCase):
    def test_captures_all_frames(self):
        exc = _make_exception()
        result = collect_locals(exc)
        self.assertIn("frames", result)
        frames = result["frames"]
        # Two frames: the module-level try and inner().
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[-1]["name"], "inner")
        self.assertIn("alpha", frames[-1]["locals"])
        self.assertIn("beta", frames[-1]["locals"])
        self.assertEqual(frames[-1]["locals"]["alpha"], "'a'")

    def test_include_filter(self):
        exc = _make_exception()
        result = collect_locals(exc, include=["alpha"])
        inner_locals = result["frames"][-1]["locals"]
        self.assertEqual(set(inner_locals.keys()), {"alpha"})

    def test_exclude_filter(self):
        exc = _make_exception()
        result = collect_locals(exc, exclude=["beta"])
        inner_locals = result["frames"][-1]["locals"]
        self.assertIn("alpha", inner_locals)
        self.assertNotIn("beta", inner_locals)

    def test_max_repr_len_truncates(self):
        def f():
            long_value = "x" * 1000
            raise RuntimeError("nope")

        try:
            f()
        except RuntimeError as exc:
            result = collect_locals(exc, max_repr_len=10)
        inner = result["frames"][-1]["locals"]
        self.assertLessEqual(len(inner["long_value"]), 13)
        self.assertTrue(inner["long_value"].endswith("..."))

    def test_max_vars_per_frame(self):
        def f():
            a = 1
            b = 2
            c = 3
            d = 4
            raise RuntimeError("nope")

        try:
            f()
        except RuntimeError as exc:
            result = collect_locals(exc, max_vars_per_frame=2)
        inner = result["frames"][-1]["locals"]
        self.assertEqual(len(inner), 2)

    def test_total_budget_truncates(self):
        def f():
            big = "y" * 5000
            raise RuntimeError("nope")

        try:
            f()
        except RuntimeError as exc:
            result = collect_locals(exc, max_total_len=100)
        self.assertTrue(result.get("truncated"))

    def test_no_truncation_flag_when_small(self):
        exc = _make_exception()
        result = collect_locals(exc, max_total_len=1_000_000)
        self.assertNotIn("truncated", result)

    def test_collector_reusable(self):
        collector = Collector(include=["alpha"])
        exc1 = _make_exception()
        exc2 = _make_exception()
        r1 = collector.capture(exc1)
        r2 = collector.capture(exc2)
        self.assertEqual(r1["frames"][-1]["locals"], r2["frames"][-1]["locals"])

    def test_repr_failure_is_isolated(self):
        class BadRepr:
            def __repr__(self):
                raise RuntimeError("cannot repr")

        def f():
            bad = BadRepr()
            raise RuntimeError("nope")

        try:
            f()
        except RuntimeError as exc:
            result = collect_locals(exc)
        inner = result["frames"][-1]["locals"]
        self.assertEqual(inner["bad"], "<unrepresentable>")

    def test_negative_limits_rejected(self):
        with self.assertRaises(ValueError):
            Collector(max_repr_len=-1)
        with self.assertRaises(ValueError):
            Collector(max_total_len=-1)
        with self.assertRaises(ValueError):
            Collector(max_vars_per_frame=-1)

    def test_none_disables_truncation(self):
        def f():
            long_value = "z" * 100
            raise RuntimeError("nope")

        try:
            f()
        except RuntimeError as exc:
            result = collect_locals(
                exc, max_repr_len=None, max_total_len=None, max_vars_per_frame=None
            )
        inner = result["frames"][-1]["locals"]
        self.assertEqual(inner["long_value"], repr("z" * 100))


if __name__ == "__main__":
    unittest.main()
